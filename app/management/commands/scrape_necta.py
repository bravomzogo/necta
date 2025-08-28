import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from app.models import School, ExamResult
import re
import os

BASE_URL = "https://onlinesys.necta.go.tz/results/{year}/{exam}/"

class Command(BaseCommand):
    help = "Scrape NECTA results for CSEE or ACSEE and rank schools"

    def add_arguments(self, parser):
        parser.add_argument("--exam", type=str, required=True, help="Exam type: CSEE or ACSEE")
        parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2023)")

    def parse_division_summary(self, soup):
        """Parse the division performance summary table from the results page"""
        div_counts = {"I": 0, "II": 0, "III": 0, "IV": 0, "0": 0}
        
        # Look for the division summary table by searching for the pattern
        # The table has specific width attributes and contains division data
        tables = soup.find_all('table')
        
        for table in tables:
            # Look for the specific pattern of the division summary table
            # It has rows with cells that have width attributes like "3%", "5%"
            rows = table.find_all('tr')
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                
                # Check if this row contains division headers
                header_text = ' '.join([cell.get_text(strip=True) for cell in cells]).upper()
                if 'I' in header_text and 'II' in header_text and 'III' in header_text and 'IV' in header_text and '0' in header_text:
                    # This is the header row, the next rows should contain data
                    if i + 2 < len(rows):
                        # Look for the "T" (Total) row which should be the third row
                        total_cells = rows[i + 2].find_all(['td', 'th'])
                        if len(total_cells) >= 6:
                            sex = total_cells[0].get_text(strip=True).upper()
                            if sex == 'T':
                                try:
                                    div_counts["I"] = int(total_cells[1].get_text(strip=True) or 0)
                                    div_counts["II"] = int(total_cells[2].get_text(strip=True) or 0)
                                    div_counts["III"] = int(total_cells[3].get_text(strip=True) or 0)
                                    div_counts["IV"] = int(total_cells[4].get_text(strip=True) or 0)
                                    div_counts["0"] = int(total_cells[5].get_text(strip=True) or 0)
                                except ValueError:
                                    pass
                                break
                    
                    # Also check if we can find the data in the immediate next row
                    if i + 1 < len(rows):
                        data_cells = rows[i + 1].find_all(['td', 'th'])
                        if len(data_cells) >= 6:
                            sex = data_cells[0].get_text(strip=True).upper()
                            if sex == 'T':
                                try:
                                    div_counts["I"] = int(data_cells[1].get_text(strip=True) or 0)
                                    div_counts["II"] = int(data_cells[2].get_text(strip=True) or 0)
                                    div_counts["III"] = int(data_cells[3].get_text(strip=True) or 0)
                                    div_counts["IV"] = int(data_cells[4].get_text(strip=True) or 0)
                                    div_counts["0"] = int(data_cells[5].get_text(strip=True) or 0)
                                except ValueError:
                                    pass
                                break
        
        # If we still haven't found the data, try a more direct approach
        if not any(div_counts.values()):
            # Look for text patterns that might contain the division data
            text = soup.get_text()
            
            # Pattern for: F 0 1 2 1 2 (Female row)
            # Pattern for: M 1 2 8 16 12 (Male row)
            # Pattern for: T 1 3 10 17 14 (Total row)
            patterns = [
                r'[Tt]\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',  # T 1 3 10 17 14
                r'Total\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',  # Total 1 3 10 17 14
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if len(match) == 5:
                        try:
                            div_counts["I"] = int(match[0])
                            div_counts["II"] = int(match[1])
                            div_counts["III"] = int(match[2])
                            div_counts["IV"] = int(match[3])
                            div_counts["0"] = int(match[4])
                            break
                        except ValueError:
                            pass
        
        return div_counts

    def handle(self, *args, **options):
        exam = options["exam"].lower()
        year = options["year"]

        if exam not in ["csee", "acsee"]:
            raise CommandError("Only CSEE and ACSEE are supported.")

        index_url = f"{BASE_URL.format(year=year, exam=exam)}/index.htm"
        self.stdout.write(f"Fetching index: {index_url}")

        try:
            resp = requests.get(index_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            raise CommandError(f"Failed to fetch {index_url}: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Filter out index files and other non-school links
        valid_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Skip index files and look for school result files
            if (href.endswith('.htm') and 
                not href.startswith('index_') and
                not href == 'index.htm' and
                not 'indexfiles' in href):
                valid_links.append(link)
        
        if not valid_links:
            # Try to debug by saving the HTML content
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            raise CommandError("No school result links found. The page structure may have changed. Saved page content to debug_page.html for inspection.")

        self.stdout.write(f"Found {len(valid_links)} schools. Scraping results...")

        for link in valid_links:
            href = link["href"]
            # Fix URL formatting - replace backslashes with forward slashes if needed
            href = href.replace('\\', '/')
            
            # Construct the full URL
            if href.startswith(('http://', 'https://')):
                school_url = href
            else:
                school_url = f"{BASE_URL.format(year=year, exam=exam)}{href}"
            
            school_text = link.text.strip()

            # Extract school code and name
            parts = school_text.split(maxsplit=1)
            if len(parts) < 2:
                code = os.path.splitext(href)[0].upper()  # Use the filename without extension as code
                name = school_text
            else:
                code, name = parts[0], parts[1]

            # Skip index files
            if 'index' in code.lower():
                continue

            # Fetch school page
            try:
                sresp = requests.get(school_url, timeout=30)
                sresp.raise_for_status()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Failed to fetch {school_url}: {e}"))
                continue

            ssoup = BeautifulSoup(sresp.text, "html.parser")
            
            # Parse division summary using the new method
            div_counts = self.parse_division_summary(ssoup)
            
            total = sum(div_counts.values()) or 1
            avg_score = (
                (div_counts["I"] * 4 + div_counts["II"] * 3 +
                 div_counts["III"] * 2 + div_counts["IV"] * 1) / total
            ) if total > 0 else 0

            school, _ = School.objects.get_or_create(code=code, defaults={"name": name})
            ExamResult.objects.update_or_create(
                school=school,
                exam=exam.upper(),
                year=year,
                defaults={
                    "division1": div_counts["I"],
                    "division2": div_counts["II"],
                    "division3": div_counts["III"],
                    "division4": div_counts["IV"],
                    "division0": div_counts["0"],
                    "total": total,
                    "average_score": avg_score,
                },
            )

            self.stdout.write(f" → {code} {name} (Div I: {div_counts['I']}, II: {div_counts['II']}, III: {div_counts['III']}, IV: {div_counts['IV']}, 0: {div_counts['0']}, Total: {total}, Avg: {avg_score:.2f})")

        self.stdout.write(self.style.SUCCESS("✅ Scraping finished."))