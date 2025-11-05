# management/commands/scrape_necta.py
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from app.models import School, ExamResult, StudentResult, SubjectPerformance
import re
import os
from urllib.parse import urljoin
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.db.models import Avg, Count

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://matokeo.necta.go.tz/results/"

class Command(BaseCommand):
    help = "Scrape NECTA results for PSLE, CSEE or ACSEE and rank schools"

    def add_arguments(self, parser):
        parser.add_argument("--exam", type=str, required=True, help="Exam type: PSLE, CSEE or ACSEE")
        parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2025)")
        parser.add_argument("--ignore-ssl", action="store_true", help="Ignore SSL certificate verification")
        parser.add_argument("--max-schools", type=int, default=0, help="Maximum number of schools to scrape (0 for all)")
        parser.add_argument("--rank-subjects", action="store_true", help="Rank subjects by average score after scraping")
        parser.add_argument("--verbose", action="store_true", help="Print detailed subject data for each school")

    def _create_session(self, ignore_ssl=False):
        """Create a requests session with retry logic"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if ignore_ssl:
            session.verify = False
        return session

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

    def clean_location_name(self, text):
        """Clean region/district names: remove MKOA WA, HALMASHAURI YA, etc."""
        text = text.strip()
        text = re.sub(r'^(MKOA WA|HALMASHAURI YA)\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(.*\)', '', text)  # Remove (CC), (DC), etc.
        return text.strip()

    def parse_psle_grade_summary(self, soup):
        """Parse PSLE grade distribution (A, B, C, D, E)"""
        grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
        tables = soup.find_all('table')
        for table in tables:
            headers = table.find_all('th')
            header_texts = [h.get_text(strip=True).upper() for h in headers]
            if 'A' in header_texts and 'B' in header_texts and 'C' in header_texts:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    if 'JUMLA' in [text.upper() for text in cell_texts]:
                        for i, header in enumerate(header_texts):
                            if header == 'A' and i < len(cell_texts):
                                grade_counts["A"] = self._parse_int(cell_texts[i])
                            elif header == 'B' and i < len(cell_texts):
                                grade_counts["B"] = self._parse_int(cell_texts[i])
                            elif header == 'C' and i < len(cell_texts):
                                grade_counts["C"] = self._parse_int(cell_texts[i])
                            elif header == 'D' and i < len(cell_texts):
                                grade_counts["D"] = self._parse_int(cell_texts[i])
                            elif header == 'E' and i < len(cell_texts):
                                grade_counts["E"] = self._parse_int(cell_texts[i])
                        break
        if not any(grade_counts.values()):
            text = soup.get_text()
            grade_pattern = r'JUMLA\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)'
            match = re.search(grade_pattern, text)
            if match:
                grade_counts["A"] = self._parse_int(match.group(1))
                grade_counts["B"] = self._parse_int(match.group(2))
                grade_counts["C"] = self._parse_int(match.group(3))
                grade_counts["D"] = self._parse_int(match.group(4))
                grade_counts["E"] = self._parse_int(match.group(5))
        return grade_counts

    def parse_psle_school_info(self, soup):
        """Parse PSLE school information including average score and performance level"""
        info = {
            'average_score': None,
            'performance_level': '',
            'total_students': 0
        }
        text = soup.get_text()
        avg_patterns = [
            r'WASTANI WA SHULE\s*:\s*([\d.]+)',
            r'WASTANI\s*:\s*([\d.]+)',
            r'Average Score\s*:\s*([\d.]+)',
            r'WASTANI WA SHULE\s*:\s*(\d+\.\d+)',
        ]
        for pattern in avg_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['average_score'] = self._parse_float(match.group(1))
                break
        level_patterns = [
            r'Daraja\s+([ABCDE])\s*\(([^)]+)\)',
            r'Grade\s+([ABCDE])\s*\(([^)]+)\)',
            r'([ABCDE])\s*\(([^)]+)\)',
            r'DARAJA\s+([ABCDE])\s*\(([^)]+)\)',
            r'font style[^>]*>DARAJA\s+([ABCDE])\s*\(([^)]+)\)',
        ]
        for pattern in level_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['performance_level'] = f"Daraja {match.group(1)} ({match.group(2)})"
                break
        total_patterns = [
            r'WALIOFANYA MTIHANI\s*:\s*(\d+)',
            r'TOTAL STUDENTS\s*:\s*(\d+)',
            r'JUMLA\s*:\s*(\d+)',
            r'WALIOFANYA\s*:\s*(\d+)',
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['total_students'] = self._parse_int(match.group(1))
                break
        return info

    def parse_psle_subjects_performance(self, soup):
        """Parse PSLE subject performance data from the specific table format"""
        subjects = []
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            header_found = False
            header_indices = {}
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
                if 'SOMO' in cell_texts and 'WASTANI WA ALAMA' in cell_texts:
                    header_found = True
                    for idx, text in enumerate(cell_texts):
                        if text == 'NAMBA':
                            header_indices['number'] = idx
                        elif text == 'SOMO':
                            header_indices['subject'] = idx
                        elif text == 'WALIOSAJILIWA':
                            header_indices['registered'] = idx
                        elif text == 'WALIOFANYA':
                            header_indices['sat'] = idx
                        elif text == 'WALIOFUTIWA/SITISHIWA':
                            header_indices['withheld'] = idx
                        elif text == 'WENYE MATOKEO':
                            header_indices['clean'] = idx
                        elif text == 'WALIOFAULU (GREDI A-C)':
                            header_indices['passed'] = idx
                        elif text == 'WASTANI WA ALAMA (/50)':
                            header_indices['average_score'] = idx
                        elif text == 'KUNDI LA UMAHIRI':
                            header_indices['proficiency'] = idx
                    break
            if header_found:
                for row in rows[i+1:]:
                    cells = row.find_all('td')
                    if len(cells) < len(header_indices):
                        continue
                    try:
                        subject_data = {
                            'CODE': cells[header_indices.get('number', 0)].get_text(strip=True),
                            'SUBJECT NAME': cells[header_indices.get('subject', 1)].get_text(strip=True),
                            'REG': self._parse_int(cells[header_indices.get('registered', 2)].get_text(strip=True)),
                            'SAT': self._parse_int(cells[header_indices.get('sat', 3)].get_text(strip=True)),
                            'W/HD': self._parse_int(cells[header_indices.get('withheld', 4)].get_text(strip=True)),
                            'CLEAN': self._parse_int(cells[header_indices.get('clean', 5)].get_text(strip=True)),
                            'PASS': self._parse_int(cells[header_indices.get('passed', 6)].get_text(strip=True)),
                            'AVERAGE SCORE': self._parse_float(cells[header_indices.get('average_score', 7)].get_text(strip=True)),
                            'PROFICIENCY GROUP': cells[header_indices.get('proficiency', 8)].get_text(strip=True) if len(cells) > header_indices.get('proficiency', 8) else ''
                        }
                        if (subject_data['SUBJECT NAME'] and
                            subject_data['SUBJECT NAME'] not in ['', 'SOMO'] and
                            subject_data['CODE'] and
                            subject_data['CODE'].isdigit()):
                            subject_data['NO-CA'] = 0
                            subjects.append(subject_data)
                    except (IndexError, ValueError, AttributeError):
                        continue
                if subjects:
                    break
        if not subjects:
            subjects = self.parse_psle_subjects_fallback(soup)
        return subjects

    def parse_psle_subjects_fallback(self, soup):
        """Fallback method to parse PSLE subjects using more flexible patterns"""
        subjects = []
        tables = soup.find_all('table', bgcolor=True)
        lightyellow_tables = [table for table in tables if 'LIGHTYELLOW' in table.get('bgcolor', '').upper()]
        for table in lightyellow_tables:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 9:
                    try:
                        subject_data = {
                            'CODE': cells[0].get_text(strip=True),
                            'SUBJECT NAME': cells[1].get_text(strip=True),
                            'REG': self._parse_int(cells[2].get_text(strip=True)),
                            'SAT': self._parse_int(cells[3].get_text(strip=True)),
                            'W/HD': self._parse_int(cells[4].get_text(strip=True)),
                            'CLEAN': self._parse_int(cells[5].get_text(strip=True)),
                            'PASS': self._parse_int(cells[6].get_text(strip=True)),
                            'AVERAGE SCORE': self._parse_float(cells[7].get_text(strip=True)),
                            'PROFICIENCY GROUP': cells[8].get_text(strip=True),
                            'NO-CA': 0
                        }
                        if subject_data['SUBJECT NAME'] and subject_data['CODE'].isdigit():
                            subjects.append(subject_data)
                    except (IndexError, ValueError, AttributeError):
                        continue
        return subjects

    def print_subject_data(self, school_name, subjects):
        """Print formatted subject data to terminal"""
        if not subjects:
            self.stdout.write(f" No subject data found for {school_name}")
            return
        self.stdout.write(f" SUBJECT PERFORMANCE FOR {school_name.upper()}:")
        self.stdout.write(" " + "="*100)
        self.stdout.write(" {:<4} {:<25} {:<8} {:<8} {:<8} {:<8} {:<12} {:<15}".format(
            "No", "Subject", "Reg", "Sat", "Pass", "Avg", "Pass%", "Proficiency"
        ))
        self.stdout.write(" " + "-"*100)
        for subject in subjects:
            pass_rate = (subject['PASS'] / subject['SAT'] * 100) if subject['SAT'] > 0 else 0
            self.stdout.write(" {:<4} {:<25} {:<8} {:<8} {:<8} {:<8.1f} {:<12.1f}% {:<15}".format(
                subject['CODE'],
                subject['SUBJECT NAME'][:24],
                subject['REG'],
                subject['SAT'],
                subject['PASS'],
                subject['AVERAGE SCORE'] or 0,
                pass_rate,
                subject['PROFICIENCY GROUP'][:14]
            ))
        self.stdout.write("")

    def parse_psle_student_results(self, soup):
        """Parse PSLE student results"""
        students = []
        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text().upper()
            if any(keyword in table_text for keyword in ['CAND. NO', 'CAND NO', 'CANDIDATE', 'PREM NO']):
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4 and cells[0].get_text(strip=True) and not cells[0].get_text(strip=True).upper() in ['CAND. NO', 'CAND NO']:
                        try:
                            candidate_data = {
                                'CNO': cells[0].get_text(strip=True),
                                'PREM_NO': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                                'SEX': cells[2].get_text(strip=True),
                                'SUBJECTS': cells[3].get_text(strip=True),
                                'AVERAGE_GRADE': ''
                            }
                            subjects_text = candidate_data['SUBJECTS']
                            avg_grade_match = re.search(r'Average Grade\s*-\s*([ABCDEF])', subjects_text, re.IGNORECASE)
                            if avg_grade_match:
                                candidate_data['AVERAGE_GRADE'] = avg_grade_match.group(1).upper()
                            students.append(candidate_data)
                        except (IndexError, ValueError):
                            continue
        return students

    def parse_school_location(self, soup, school_name):
        """Fallback: Parse location from school page or name"""
        location = {
            'region': 'Unknown',
            'district': 'Unknown',
            'council': 'Unknown'
        }
        text = soup.get_text()
        tanzania_regions = [
            "Dar es Salaam", "Arusha", "Dodoma", "Mwanza", "Mbeya", "Tanga", "Morogoro",
            "Kagera", "Mtwara", "Kilimanjaro", "Tabora", "Singida", "Rukwa", "Kigoma",
            "Shinyanga", "Mara", "Manyara", "Ruvuma", "Lindi", "Pwani", "Geita", "Katavi",
            "Njombe", "Simiyu", "Songwe", "Iringa", "Mjini Magharibi", "Kaskazini Pemba", "Kusini Pemba"
        ]
        name_parts = school_name.split(' - ')
        if len(name_parts) > 1:
            location_part = name_parts[-1].strip()
            for region in tanzania_regions:
                if region.lower() in location_part.lower():
                    location['region'] = region
                    break
        if location['region'] == 'Unknown':
            for region in tanzania_regions:
                if region.lower() in text.lower():
                    location['region'] = region
                    break
        if location['district'] == 'Unknown':
            district_indicators = ['MC', 'DC', 'MUNICIPAL', 'DISTRICT']
            for indicator in district_indicators:
                if indicator in school_name.upper():
                    name_parts = school_name.split()
                    for i, part in enumerate(name_parts):
                        if part.upper() in district_indicators and i > 0:
                            location['district'] = ' '.join(name_parts[:i])
                            break
                    break
        return location

    def get_links_from_page(self, session, page_url):
        """Extract all links from a page"""
        try:
            resp = session.get(page_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.text.strip()
                if href.endswith('.htm'):
                    full_url = urljoin(page_url, href)
                    links.append({
                        'href': href,
                        'text': text,
                        'url': full_url
                    })
            return links
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Failed to fetch page {page_url}: {e}"))
            return []

    def rank_psle_subjects(self, year):
        """Rank PSLE subjects by average score across all schools"""
        self.stdout.write(f"\n Ranking PSLE Subjects by Average Score ({year})")
        self.stdout.write("="*80)
        subject_performances = SubjectPerformance.objects.filter(
            exam_result__exam='PSLE',
            exam_result__year=year,
            average_score__isnull=False
        ).select_related('exam_result__school')
        subject_stats = {}
        for subject in subject_performances:
            subject_name = subject.subject_name
            if subject_name not in subject_stats:
                subject_stats[subject_name] = {
                    'scores': [],
                    'schools_count': 0,
                    'total_registered': 0,
                    'total_passed': 0
                }
            subject_stats[subject_name]['scores'].append(subject.average_score)
            subject_stats[subject_name]['schools_count'] += 1
            subject_stats[subject_name]['total_registered'] += subject.registered
            subject_stats[subject_name]['total_passed'] += subject.passed
        ranked_subjects = []
        for subject_name, stats in subject_stats.items():
            if stats['scores']:
                avg_score = sum(stats['scores']) / len(stats['scores'])
                pass_rate = (stats['total_passed'] / stats['total_registered'] * 100) if stats['total_registered'] > 0 else 0
                ranked_subjects.append({
                    'subject_name': subject_name,
                    'average_score': avg_score,
                    'schools_count': stats['schools_count'],
                    'total_registered': stats['total_registered'],
                    'total_passed': stats['total_passed'],
                    'pass_rate': pass_rate,
                    'min_score': min(stats['scores']),
                    'max_score': max(stats['scores'])
                })
        ranked_subjects.sort(key=lambda x: x['average_score'], reverse=True)
        self.stdout.write(f"\n{'Rank':<4} {'Subject Name':<25} {'Avg Score':<12} {'Pass Rate':<10} {'Schools':<8} {'Students':<10}")
        self.stdout.write("-" * 80)
        for rank, subject in enumerate(ranked_subjects, 1):
            self.stdout.write(
                f"{rank:<4} {subject['subject_name']:<25} "
                f"{subject['average_score']:<12.2f} "
                f"{subject['pass_rate']:<10.1f}% "
                f"{subject['schools_count']:<8} "
                f"{subject['total_registered']:<10}"
            )
        filename = f"psle_subject_rankings_{year}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"PSLE {year} - Subject Rankings by Average Score\n")
            f.write("="*80 + "\n")
            f.write(f"{'Rank':<4} {'Subject Name':<25} {'Avg Score':<12} {'Pass Rate':<10} {'Schools':<8} {'Students':<10} {'Range':<15}\n")
            f.write("-" * 80 + "\n")
            for rank, subject in enumerate(ranked_subjects, 1):
                f.write(
                    f"{rank:<4} {subject['subject_name']:<25} "
                    f"{subject['average_score']:<12.2f} "
                    f"{subject['pass_rate']:<10.1f}% "
                    f"{subject['schools_count']:<8} "
                    f"{subject['total_registered']:<10} "
                    f"{subject['min_score']:.1f}-{subject['max_score']:.1f}\n"
                )
            f.write("\n" + "="*80 + "\n")
            f.write("SUMMARY STATISTICS:\n")
            f.write(f"Total Subjects: {len(ranked_subjects)}\n")
            f.write(f"Total Schools: {sum(s['schools_count'] for s in ranked_subjects)}\n")
            f.write(f"Total Students: {sum(s['total_registered'] for s in ranked_subjects)}\n")
            if ranked_subjects:
                best = ranked_subjects[0]
                worst = ranked_subjects[-1]
                f.write(f"Best Subject: {best['subject_name']} (Avg: {best['average_score']:.2f})\n")
                f.write(f"Worst Subject: {worst['subject_name']} (Avg: {worst['average_score']:.2f})\n")
        self.stdout.write(self.style.SUCCESS(f" Subject rankings saved to {filename}"))
        return ranked_subjects

    def process_school_page(self, session, link_info, exam, year, all_results, verbose=False, region_name=None, district_name=None):
        """Process an individual school page and return 1 if successful"""
        school_url = link_info['url']
        school_text = link_info['text']
        
        # FIXED: Properly parse school name and code from text like "ALBEHIJE PRIMARY SCHOOL - PS0101114"
        if ' - ' in school_text:
            # Split by " - " to separate name from code
            name_part, code_part = school_text.split(' - ', 1)
            name = name_part.strip()
            code = code_part.strip()
        else:
            # Fallback: try to extract code from URL
            code = os.path.splitext(os.path.basename(link_info['href']))[0].upper()
            name = school_text
        
        try:
            sresp = session.get(school_url, timeout=30)
            sresp.raise_for_status()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Failed to fetch {school_url}: {e}"))
            return 0
        
        ssoup = BeautifulSoup(sresp.text, "html.parser")

        # Use passed region/district first
        location = {
            'region': region_name or 'Unknown',
            'district': district_name or 'Unknown',
            'council': 'Unknown'
        }

        # Fallback only if still unknown
        if location['region'] == 'Unknown' or location['district'] == 'Unknown':
            fallback = self.parse_school_location(ssoup, name)
            location['region'] = location['region'] if location['region'] != 'Unknown' else fallback['region']
            location['district'] = location['district'] if location['district'] != 'Unknown' else fallback['district']
            location['council'] = fallback['council']

        if exam == "psle":
            grade_counts = self.parse_psle_grade_summary(ssoup)
            school_info = self.parse_psle_school_info(ssoup)
            subjects = self.parse_psle_subjects_performance(ssoup)
            students = self.parse_psle_student_results(ssoup)
            average_score = school_info['average_score']
            performance_level = school_info['performance_level']
            total = school_info['total_students'] or sum(grade_counts.values())
            if average_score is None:
                self.stdout.write(self.style.WARNING(f"Average score not found for {code} {name}, skipping."))
                return 0
        else:
            return 0

        self.stdout.write(f" → {code} {name}")
        self.stdout.write(f"   Region: {location['region']}, District: {location['district']}")
        self.stdout.write(f"   Grades - A: {grade_counts['A']}, B: {grade_counts['B']}, C: {grade_counts['C']}, D: {grade_counts['D']}, E: {grade_counts['E']}")
        self.stdout.write(f"   Total: {total}, Average: {average_score}, Level: {performance_level}")
        self.stdout.write(f"   Subjects: {len(subjects)}, Students: {len(students)}")
        
        if verbose and subjects:
            self.print_subject_data(name, subjects)

        # Create or update school with proper name and code
        school, created = School.objects.get_or_create(
            code=code,  # This will be "PS0101114"
            defaults={
                "name": name,  # This will be "ALBEHIJE PRIMARY SCHOOL"
                "region": location['region'],
                "district": location['district'],
                "council": location['council'],
                "school_type": "Primary"
            }
        )
        
        # Update school if location information improved
        update_fields = {}
        if school.region == "Unknown" and location['region'] != "Unknown":
            update_fields['region'] = location['region']
        if school.district == "Unknown" and location['district'] != "Unknown":
            update_fields['district'] = location['district']
        if school.council == "Unknown" and location['council'] != "Unknown":
            update_fields['council'] = location['council']
        
        if update_fields:
            for field, value in update_fields.items():
                setattr(school, field, value)
            school.save()

        if exam == "psle":
            exam_result, created = ExamResult.objects.update_or_create(
                school=school,
                exam=exam.upper(),
                year=year,
                defaults={
                    "grade_a": grade_counts["A"],
                    "grade_b": grade_counts["B"],
                    "grade_c": grade_counts["C"],
                    "grade_d": grade_counts["D"],
                    "grade_e": grade_counts["E"],
                    "grade_f": grade_counts["F"],
                    "average_score": average_score,
                    "performance_level": performance_level,
                    "total": total,
                },
            )
            
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
                        'average_score': subject_data.get('AVERAGE SCORE'),
                        'proficiency_group': subject_data.get('PROFICIENCY GROUP', ''),
                    }
                )
            
            for student_data in students:
                StudentResult.objects.update_or_create(
                    exam_result=exam_result,
                    candidate_number=student_data['CNO'],
                    defaults={
                        "prem_number": student_data['PREM_NO'],
                        "sex": student_data['SEX'],
                        "subjects": student_data['SUBJECTS'],
                        "average_grade": student_data['AVERAGE_GRADE'],
                    }
                )
            
            all_results.append({
                "code": code,
                "name": name,
                "region": location['region'],
                "district": location['district'],
                "council": location['council'],
                "average_score": average_score,
                "performance_level": performance_level,
                "grade_a": grade_counts["A"],
                "grade_b": grade_counts["B"],
                "grade_c": grade_counts["C"],
                "grade_d": grade_counts["D"],
                "grade_e": grade_counts["E"],
                "total": total,
            })
        
        return 1

    def handle(self, *args, **options):
        exam = options["exam"].lower()
        year = options["year"]
        ignore_ssl = options["ignore_ssl"]
        max_schools = options["max_schools"]
        rank_subjects = options["rank_subjects"]
        verbose = options["verbose"]

        if exam not in ["psle", "csee", "acsee"]:
            raise CommandError("Only PSLE, CSEE and ACSEE are supported.")

        session = self._create_session(ignore_ssl)
        index_url = f"{BASE_URL}{year}/psle/psle.htm" if exam == "psle" else f"{BASE_URL}{year}/{exam}/index.htm"

        self.stdout.write(f"Fetching index: {index_url}")
        try:
            resp = session.get(index_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            raise CommandError(f"Failed to fetch index page: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")
        regional_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.text.strip()
            if href.startswith('results/') and 'reg_' in href and href.endswith('.htm'):
                full_url = urljoin(index_url, href)
                regional_links.append({
                    'href': href,
                    'text': text,
                    'url': full_url
                })

        if not regional_links:
            with open("debug_index.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            raise CommandError("No regional links found. Saved index page to debug_index.html for inspection.")

        self.stdout.write(f"Found {len(regional_links)} regional directories. Processing...")
        all_results = []
        schools_processed = 0

        for regional_link in regional_links:
            if max_schools > 0 and schools_processed >= max_schools:
                break

            region_name = self.clean_location_name(regional_link['text'])
            regional_url = regional_link['url']
            self.stdout.write(f"Processing regional directory: {region_name}")

            district_links = self.get_links_from_page(session, regional_url)
            district_links = [link for link in district_links if 'distr_' in link['href']]
            self.stdout.write(f" Found {len(district_links)} districts in {region_name}")

            for district_link in district_links:
                if max_schools > 0 and schools_processed >= max_schools:
                    break

                district_name = self.clean_location_name(district_link['text'])
                district_url = district_link['url']
                self.stdout.write(f" Processing district: {district_name}")

                school_links = self.get_links_from_page(session, district_url)
                school_links = [link for link in school_links if link['href'].startswith('shl_')]
                self.stdout.write(f" Found {len(school_links)} schools in {district_name}")

                for school_link in school_links:
                    if max_schools > 0 and schools_processed >= max_schools:
                        break

                    processed = self.process_school_page(
                        session, school_link, exam, year, all_results, verbose,
                        region_name=region_name,
                        district_name=district_name
                    )
                    if processed:
                        schools_processed += 1
                        self.stdout.write(f" [{schools_processed}] Successfully processed school")

        self.stdout.write(self.style.SUCCESS(f"Scraping finished. Processed {schools_processed} schools."))

        if exam == "psle" and all_results:
            all_results.sort(key=lambda x: x["average_score"], reverse=True)
            self.stdout.write(f"\n Ranking schools by Average Score (higher is better) - PSLE {year}:")
            for rank, result in enumerate(all_results, start=1):
                self.stdout.write(f"{rank}. {result['code']} {result['name']} (Region: {result['region']}, District: {result['district']}) - Average: {result['average_score']} - {result['performance_level']}")
        elif all_results:
            all_results.sort(key=lambda x: x["gpa"])
            self.stdout.write(f"\nRanking schools by GPA (lower is better) - {exam.upper()} {year}:")
            for rank, result in enumerate(all_results, start=1):
                self.stdout.write(f"{rank}. {result['code']} {result['name']} (Region: {result['region']}) - GPA: {result['gpa']}")
        else:
            self.stdout.write(self.style.WARNING("No schools were successfully processed."))

        if all_results:
            if exam == "psle":
                filename = f"psle_school_results_{year}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"PSLE {year} - School Rankings by Average Score\n")
                    f.write("="*100 + "\n")
                    f.write("Rank. School Code School Name - Region - District - Council - Average Score - Performance Level\n")
                    f.write("="*100 + "\n")
                    for rank, result in enumerate(all_results, start=1):
                        f.write(f"{rank}. {result['code']} {result['name']} - {result['region']} - {result['district']} - {result['council']} - Average: {result['average_score']} - {result['performance_level']}\n")
                        f.write(f" Grades: A:{result['grade_a']} B:{result['grade_b']} C:{result['grade_c']} D:{result['grade_d']} E:{result['grade_e']} Total:{result['total']}\n\n")
            else:
                filename = f"school_results_{year}_{exam}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"{exam.upper()} {year} - School Rankings by GPA\n")
                    f.write("="*80 + "\n")
                    f.write("Rank. School Code School Name - Region - GPA\n")
                    f.write("="*80 + "\n")
                    for rank, result in enumerate(all_results, start=1):
                        f.write(f"{rank}. {result['code']} {result['name']} - {result['region']} - GPA: {result['gpa']}\n")
            self.stdout.write(self.style.SUCCESS(f" Results saved to {filename}"))

        if exam == "psle" and rank_subjects:
            self.rank_psle_subjects(year)