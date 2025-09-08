import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from app.models import School, ExamResult, StudentResult, SubjectPerformance
import re
import os
from urllib.parse import urljoin

BASE_URL = "https://onlinesys.necta.go.tz/results/{year}/{exam}/"

class Command(BaseCommand):
    help = "Scrape NECTA results for CSEE or ACSEE and rank schools"

    def add_arguments(self, parser):
        parser.add_argument("--exam", type=str, required=True, help="Exam type: CSEE or ACSEE")
        parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2023)")

    def _parse_int(self, value):
        try:
            return int(value) if value else 0
        except ValueError:
            return 0

    def _parse_float(self, value):
        try:
            return float(value) if value else None
        except ValueError:
            return None

    def parse_division_summary(self, soup):
        div_counts = {"I": 0, "II": 0, "III": 0, "IV": 0, "0": 0}
        division_table = None
        tables = soup.find_all('table')
        for table in tables:
            if 'DIVISION PERFORMANCE SUMMARY' in table.get_text():
                division_table = table
                break
        
        if division_table:
            rows = division_table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 6 and cells[0].get_text(strip=True).upper() == 'T':
                    try:
                        div_counts["I"] = int(cells[1].get_text(strip=True) or 0)
                        div_counts["II"] = int(cells[2].get_text(strip=True) or 0)
                        div_counts["III"] = int(cells[3].get_text(strip=True) or 0)
                        div_counts["IV"] = int(cells[4].get_text(strip=True) or 0)
                        div_counts["0"] = int(cells[5].get_text(strip=True) or 0)
                    except ValueError:
                        pass
                    break
        
        if not any(div_counts.values()):
            text = soup.get_text()
            patterns = [
                r'[Tt]\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
                r'Total\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
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

    def parse_overall_performance(self, soup):
        overall = {}
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True).upper()
                    value = cells[1].get_text(strip=True)
                    overall[key] = value
        return overall

    def parse_division_performance(self, soup):
        division_perf = {}
        tables = soup.find_all('table')
        for table in tables:
            if 'EXAMINATION CENTRE DIVISION PERFORMANCE' in table.get_text():
                rows = table.find_all('tr')
                if len(rows) > 1:
                    headers = [cell.get_text(strip=True) for cell in rows[0].find_all('td')]
                    values = [cell.get_text(strip=True) for cell in rows[1].find_all('td')]
                    for h, v in zip(headers, values):
                        division_perf[h] = v
                break
        return division_perf

    def parse_subjects_performance(self, soup):
        subjects = []
        
        # Method 1: Direct parsing for subject codes
        subjects = self.parse_subjects_direct(soup)
        if subjects:
            return subjects
        
        # Method 2: Header-based parsing
        subject_patterns = [
            "EXAMINATION CENTRE SUBJECTS PERFORMANCE",
            "SUBJECTS PERFORMANCE",
            "SUBJECT PERFORMANCE"
        ]
        
        for pattern in subject_patterns:
            subject_header = soup.find(string=re.compile(pattern, re.IGNORECASE))
            if subject_header:
                # Find parent table and look for data
                parent_table = subject_header.find_parent('table')
                if parent_table:
                    # Check all subsequent tables
                    next_elements = parent_table.find_next_siblings()
                    for element in next_elements:
                        if element.name == 'table':
                            subjects = self._parse_subject_table(element)
                            if subjects:
                                return subjects
                    
                    # Also check the parent table itself
                    subjects = self._parse_subject_table(parent_table)
                    if subjects:
                        return subjects
        
        return subjects

    def _parse_subject_table(self, table):
        """Parse a table for subject data"""
        subjects = []
        rows = table.find_all('tr')
        
        # Find header row
        header_row_idx = -1
        headers = []
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
            
            if (any('CODE' in text for text in cell_texts) and 
                any('SUBJECT' in text for text in cell_texts) and
                len(cells) >= 8):
                header_row_idx = i
                headers = cell_texts
                break
        
        if header_row_idx == -1:
            return subjects
        
        # Process data rows
        for row in rows[header_row_idx + 1:]:
            cells = row.find_all('td')
            if len(cells) < 8:
                continue
            
            # Check if first cell looks like a subject code
            first_cell_text = cells[0].get_text(strip=True)
            if not re.match(r'^\d{2,3}$', first_cell_text):
                continue
            
            subject_data = {}
            for i, cell in enumerate(cells):
                if i >= len(headers):
                    break
                header = headers[i]
                value = cell.get_text(strip=True)
                
                # Map headers to standardized names
                if 'CODE' in header:
                    subject_data['CODE'] = value
                elif 'SUBJECT' in header and 'NAME' in header:
                    subject_data['SUBJECT NAME'] = value
                elif 'SUBJECT' in header and not subject_data.get('SUBJECT NAME'):
                    subject_data['SUBJECT NAME'] = value
                elif 'REG' in header or 'REGISTERED' in header:
                    subject_data['REG'] = value
                elif 'SAT' in header:
                    subject_data['SAT'] = value
                elif 'NO-CA' in header or 'NOCA' in header:
                    subject_data['NO-CA'] = value
                elif 'W/HD' in header or 'WITHHELD' in header:
                    subject_data['W/HD'] = value
                elif 'CLEAN' in header:
                    subject_data['CLEAN'] = value
                elif 'PASS' in header:
                    subject_data['PASS'] = value
                elif 'GPA' in header or 'CPA' in header:
                    subject_data['GPA'] = value
                elif 'COMPENTENCY' in header or 'COMPETENCY' in header or 'LEVEL' in header:
                    subject_data['COMPENTENCY LEVEL'] = value
            
            # Convert numeric values
            for field in ['REG', 'SAT', 'NO-CA', 'W/HD', 'CLEAN', 'PASS']:
                if field in subject_data:
                    subject_data[field] = self._parse_int(subject_data[field])
            
            # Convert GPA
            if 'GPA' in subject_data:
                subject_data['GPA'] = self._parse_float(subject_data['GPA'])
            
            if subject_data.get('CODE') and subject_data.get('SUBJECT NAME'):
                subjects.append(subject_data)
        
        return subjects

    def parse_subjects_direct(self, soup):
        """Direct parsing approach for subject tables"""
        subjects = []
        
        # Look for all tables
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 9:  # Need enough columns for subject data
                    first_cell = cells[0].get_text(strip=True)
                    
                    # Check if this looks like a subject code row
                    if re.match(r'^\d{2,3}$', first_cell):
                        subject_data = {
                            'CODE': first_cell,
                            'SUBJECT NAME': cells[1].get_text(strip=True),
                            'REG': self._parse_int(cells[2].get_text(strip=True)),
                            'SAT': self._parse_int(cells[3].get_text(strip=True)),
                            'NO-CA': self._parse_int(cells[4].get_text(strip=True)),
                            'W/HD': self._parse_int(cells[5].get_text(strip=True)),
                            'CLEAN': self._parse_int(cells[6].get_text(strip=True)),
                            'PASS': self._parse_int(cells[7].get_text(strip=True)),
                            'GPA': self._parse_float(cells[8].get_text(strip=True)),
                        }
                        
                        # Try to get competency level if available
                        if len(cells) > 9:
                            subject_data['COMPENTENCY LEVEL'] = cells[9].get_text(strip=True)
                        
                        subjects.append(subject_data)
        
        return subjects

    def parse_student_results(self, soup):
        students = []
        tables = soup.find_all('table')
        for table in tables:
            if 'CNO' in table.get_text() and 'SEX' in table.get_text() and 'AGGT' in table.get_text() and 'DIV' in table.get_text():
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 5:
                        cno = cells[0].get_text(strip=True)
                        sex = cells[1].get_text(strip=True)
                        aggt = cells[2].get_text(strip=True)
                        div = cells[3].get_text(strip=True)
                        subjects = cells[4].get_text(strip=True)
                        students.append({
                            'CNO': cno,
                            'SEX': sex,
                            'AGGT': aggt,
                            'DIV': div,
                            'DETAILED SUBJECTS': subjects
                        })
                break
        return students

    def parse_school_region(self, soup, school_name):
        # Try to extract region from the page content
        text = soup.get_text()
        
        # Common Tanzanian regions to look for
        tanzania_regions = [
            "Dar es Salaam", "Arusha", "Dodoma", "Mwanza", "Mbeya", "Tanga", "Morogoro",
            "Kagera", "Mtwara", "Kilimanjaro", "Tabora", "Singida", "Rukwa", "Kigoma",
            "Shinyanga", "Mara", "Manyara", "Ruvuma", "Lindi", "Pwani", "Geita", "Katavi",
            "Njombe", "Simiyu", "Songwe", "Iringa", "Mjini Magharibi", "Kaskazini Pemba", "Kusini Pemba"
        ]
        
        # Look for region patterns in the text
        region = "Unknown"
        for reg in tanzania_regions:
            if reg.lower() in text.lower():
                region = reg
                break
        
        # If region not found in text, try to infer from school name
        if region == "Unknown":
            for reg in tanzania_regions:
                if reg.lower() in school_name.lower():
                    region = reg
                    break
        
        return region

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
        
        valid_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if (href.endswith('.htm') and 
                not href.startswith('index_') and
                not href == 'index.htm' and
                not 'indexfiles' in href):
                valid_links.append(link)
        
        if not valid_links:
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            raise CommandError("No school result links found. The page structure may have changed. Saved page content to debug_page.html for inspection.")

        self.stdout.write(f"Found {len(valid_links)} schools. Scraping results...")

        all_results = []

        for link in valid_links:
            href = link["href"]
            href = href.replace('\\', '/')
            
            if href.startswith(('http://', 'https://')):
                school_url = href
            else:
                school_url = urljoin(BASE_URL.format(year=year, exam=exam), href)
            
            school_text = link.text.strip()

            parts = school_text.split(maxsplit=1)
            if len(parts) < 2:
                code = os.path.splitext(href)[0].upper()
                name = school_text
            else:
                code, name = parts[0], parts[1]

            if 'index' in code.lower() or not code.startswith('S'):
                continue

            try:
                sresp = requests.get(school_url, timeout=30)
                sresp.raise_for_status()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Failed to fetch {school_url}: {e}"))
                continue

            ssoup = BeautifulSoup(sresp.text, "html.parser")
            
            # Debug: Save HTML for inspection if needed
            if not os.path.exists("debug_html"):
                os.makedirs("debug_html")
            with open(f"debug_html/school_{code}.html", "w", encoding="utf-8") as f:
                f.write(sresp.text)
            
            div_counts = self.parse_division_summary(ssoup)
            overall = self.parse_overall_performance(ssoup)
            division_perf = self.parse_division_performance(ssoup)
            subjects = self.parse_subjects_performance(ssoup)
            students = self.parse_student_results(ssoup)
            
            # Extract region information
            region = self.parse_school_region(ssoup, name)
            
            gpa_str = overall.get('EXAMINATION CENTRE GPA', '')
            gpa_match = re.search(r'([\d.]+)', gpa_str)
            gpa = float(gpa_match.group(1)) if gpa_match else None
            
            if gpa is None:
                self.stdout.write(self.style.WARNING(f"⚠️ GPA not found for {code} {name}, skipping."))
                continue

            total = int(division_perf.get('CLEAN', sum(div_counts.values()))) or 1

            school, _ = School.objects.get_or_create(
                code=code, 
                defaults={
                    "name": name,
                    "region": region
                }
            )
            
            # Update region if it was previously unknown
            if school.region == "Unknown" and region != "Unknown":
                school.region = region
                school.save()

            exam_result, created = ExamResult.objects.update_or_create(
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
                    "gpa": gpa,
                },
            )

            # Save subject performance data
            for subject_data in subjects:
                SubjectPerformance.objects.update_or_create(
                    exam_result=exam_result,
                    subject_code=subject_data.get('CODE', ''),
                    defaults={
                        'subject_name': subject_data.get('SUBJECT NAME', ''),
                        'registered': subject_data.get('REG', 0),
                        'sat': subject_data.get('SAT', 0),
                        'no_ca': subject_data.get('NO-CA', 0),
                        'withheld': subject_data.get('W/HD', 0),
                        'clean': subject_data.get('CLEAN', 0),
                        'passed': subject_data.get('PASS', 0),
                        'gpa': subject_data.get('GPA'),
                        'competency_level': subject_data.get('COMPENTENCY LEVEL', ''),
                    }
                )

            # Save student results
            for student_data in students:
                StudentResult.objects.update_or_create(
                    exam_result=exam_result,
                    candidate_number=student_data['CNO'],
                    defaults={
                        "sex": student_data['SEX'],
                        "aggregate_score": student_data['AGGT'],
                        "division": student_data['DIV'],
                        "subjects": student_data['DETAILED SUBJECTS'],
                    }
                )

            # Store result for ranking later
            all_results.append({
                "code": code,
                "name": name,
                "region": region,
                "gpa": gpa,
                "div1": div_counts["I"],
                "div2": div_counts["II"],
                "div3": div_counts["III"],
                "div4": div_counts["IV"],
                "div0": div_counts["0"],
                "total": total,
                "subjects": [
                    {
                        "code": subject_data.get('CODE', ''),
                        "name": subject_data.get('SUBJECT NAME', ''),
                        "gpa": subject_data.get('GPA'),
                        "competency_level": subject_data.get('COMPENTENCY LEVEL', '')
                    } for subject_data in subjects if subject_data.get('GPA') is not None
                ]
            })

            self.stdout.write(f" → {code} {name} (Region: {region}, Div I: {div_counts['I']}, II: {div_counts['II']}, III: {div_counts['III']}, IV: {div_counts['IV']}, 0: {div_counts['0']}, Total: {total}, GPA: {gpa})")
            self.stdout.write(f"   Found {len(subjects)} subjects")
            
            # Debug output for subject parsing
            if not subjects:
                self.stdout.write(self.style.WARNING(f"   ⚠️ No subjects found for {code}"))
                # Print sample of HTML to help debug
                sample_text = ssoup.get_text()[:500]
                self.stdout.write(self.style.WARNING(f"   Sample HTML text: {sample_text}..."))

        self.stdout.write(self.style.SUCCESS("✅ Scraping finished."))

        # Rank schools by GPA
        all_results.sort(key=lambda x: x["gpa"])
        self.stdout.write("\nRanking schools by GPA (lower is better):")
        for rank, result in enumerate(all_results, start=1):
            self.stdout.write(f"{rank}. {result['code']} {result['name']} (Region: {result['region']}) - GPA: {result['gpa']}")

            # Rank subjects by GPA for this school
            if result['subjects']:
                self.stdout.write(f"  Subject Rankings for {result['code']} {result['name']}:")
                sorted_subjects = sorted(result['subjects'], key=lambda x: x['gpa'] or float('inf'))
                for subj_rank, subject in enumerate(sorted_subjects, start=1):
                    self.stdout.write(f"    {subj_rank}. {subject['name']} (Code: {subject['code']}) - GPA: {subject['gpa']} ({subject['competency_level']})")

        # Save results to a text file
        with open(f"school_results_{year}_{exam}.txt", "w", encoding="utf-8") as f:
            f.write("Rank. School Code School Name - Region - GPA\n")
            f.write("="*80 + "\n")
            for rank, result in enumerate(all_results, start=1):
                f.write(f"{rank}. {result['code']} {result['name']} - {result['region']} - GPA: {result['gpa']}\n")
                if result['subjects']:
                    f.write(f"  Subject Rankings:\n")
                    sorted_subjects = sorted(result['subjects'], key=lambda x: x['gpa'] or float('inf'))
                    for subj_rank, subject in enumerate(sorted_subjects, start=1):
                        f.write(f"    {subj_rank}. {subject['name']} (Code: {subject['code']}) - GPA: {subject['gpa']} ({subject['competency_level']})\n")
                    f.write("\n")

        self.stdout.write(self.style.SUCCESS(f"✅ Results saved to school_results_{year}_{exam}.txt"))