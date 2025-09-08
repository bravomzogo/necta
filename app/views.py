import json
import re
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Avg, Count, Q
from .models import ExamResult, School, StudentResult, SubjectPerformance
from .services import get_ranked_schools

def school_rankings(request, exam_type, year):
    # Get ranked schools using the scraped data
    results = get_ranked_schools(exam_type, year)
    
    # Calculate statistics for the charts
    total_schools = results.count()
    total_students = results.aggregate(total=Sum('total'))['total'] or 0
    
    # Only calculate average if we have schools with valid GPAs
    valid_results = results.exclude(gpa=0)
    avg_gpa_all = valid_results.aggregate(avg=Avg('gpa'))['avg'] or 0 if valid_results.exists() else 0
    
    best_gpa = results.first().gpa if results else 0
    
    # Division totals
    division_totals = results.aggregate(
        div1=Sum('division1'),
        div2=Sum('division2'),
        div3=Sum('division3'),
        div4=Sum('division4'),
        div0=Sum('division0')
    )
    
    # GPA distribution - NECTA: lower GPAs are better (1.0-2.0 is excellent)
    gpa_ranges = {
        '1_2': results.filter(gpa__gte=1.0, gpa__lt=2.0).count(),
        '2_3': results.filter(gpa__gte=2.0, gpa__lt=3.0).count(),
        '3_4': results.filter(gpa__gte=3.0, gpa__lt=4.0).count(),
        '4_plus': results.filter(gpa__gte=4.0).count(),
    }
    
    # Get unique regions from the current results
    regions = list(results.values_list('school__region', flat=True).distinct()
                  .exclude(school__region='Unknown')
                  .exclude(school__region__isnull=True)
                  .order_by('school__region'))
    
    # Add ranking position to each result
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'gpa': result.gpa,
            'division1': result.division1,
            'division2': result.division2,
            'division3': result.division3,
            'division4': result.division4,
            'division0': result.division0,
            'total': result.total,
        })
    
    context = {
        'results': ranked_results,
        'regions': regions,  # Added this line
        'exam_type': exam_type,
        'year': year,
        'total_schools': total_schools,
        'total_students': total_students,
        'avg_gpa_all': round(avg_gpa_all, 2),
        'best_gpa': round(best_gpa, 4) if best_gpa else 0,
        'division1_total': division_totals['div1'] or 0,
        'division2_total': division_totals['div2'] or 0,
        'division3_total': division_totals['div3'] or 0,
        'division4_total': division_totals['div4'] or 0,
        'division0_total': division_totals['div0'] or 0,
        'gpa_1_2': gpa_ranges['1_2'],
        'gpa_2_3': gpa_ranges['2_3'],
        'gpa_3_4': gpa_ranges['3_4'],
        'gpa_4_plus': gpa_ranges['4_plus'],
    }
    
    return render(request, "rankings.html", context)

def home(request):
    # Get available years and exam types for the dropdown
    years = list(ExamResult.objects.values_list('year', flat=True).distinct().order_by('-year'))
    
    # Get unique exam types and convert to a set to remove duplicates, then back to sorted list
    exam_types_queryset = ExamResult.objects.values_list('exam', flat=True).distinct()
    exam_types = sorted(set(exam_types_queryset))
    
    regions = list(School.objects.values_list('region', flat=True).distinct()
                 .exclude(region='Unknown').exclude(region__isnull=True).order_by('region'))
    
    # Get some statistics for the home page
    total_schools = School.objects.count()
    
    # Get top schools for ACSEE 2023
    top_schools = ExamResult.objects.filter(year=2023, exam='ACSEE').select_related('school').order_by('gpa')[:5]
    
    # Safely get the latest year for other purposes
    latest_year = ExamResult.objects.latest('year').year if ExamResult.objects.exists() else None
    
    context = {
        'years': years,
        'exam_types': exam_types,
        'regions': regions,
        'top_schools': top_schools,
        'latest_year': latest_year,
        'total_schools': total_schools,
    }
    return render(request, "home.html", context)


# from django.shortcuts import render, get_object_or_404
# from app.models import School, ExamResult, StudentResult, SubjectPerformance
# import json
# import re

def school_detail(request, school_id):
    # Get school details and all its exam results
    school = get_object_or_404(School, id=school_id)
    results = ExamResult.objects.filter(school=school).order_by('-year', 'exam')
    
    # Initialize variables
    student_results = []
    latest_year = None
    latest_exam = None
    subject_data_for_js = {}  # For grade distribution charts
    subject_performances = []  # For GPA-based subject rankings
    school_ranking = None
    total_schools_in_exam = 0
    
    if results.exists():
        latest_result = results.first()
        latest_year = latest_result.year
        latest_exam = latest_result.exam
        
        # Get school's ranking position for the latest exam
        if latest_year and latest_exam:
            ranked_schools = ExamResult.objects.filter(
                exam=latest_exam,
                year=latest_year,
                gpa__gt=0
            ).select_related('school').order_by('gpa', '-total')
            
            total_schools_in_exam = ranked_schools.count()
            
            # Convert to list to get ranking position
            ranked_list = list(ranked_schools)
            for rank, result in enumerate(ranked_list, start=1):
                if result.school.id == school.id:
                    school_ranking = rank
                    break
        
        # Get student results for the latest exam result
        student_results = StudentResult.objects.filter(
            exam_result=latest_result
        ).order_by('candidate_number')
        
        # Get subject performance data for the latest exam result
        subject_performances = SubjectPerformance.objects.filter(
            exam_result=latest_result
        ).order_by('gpa')
        
        # Get subject rankings compared to all other schools
        if latest_year and latest_exam:
            from django.db.models import Avg, Count
            
            # Get all subject performances for this exam year
            all_subject_performances = SubjectPerformance.objects.filter(
                exam_result__exam=latest_exam,
                exam_result__year=latest_year,
                gpa__isnull=False
            ).select_related('exam_result__school')
            
            # Group by subject code and create rankings
            subject_rankings = {}
            for subject_perf in all_subject_performances:
                subject_code = subject_perf.subject_code
                if subject_code not in subject_rankings:
                    subject_rankings[subject_code] = []
                subject_rankings[subject_code].append({
                    'school_id': subject_perf.exam_result.school.id,
                    'school_name': subject_perf.exam_result.school.name,
                    'gpa': subject_perf.gpa,
                    'subject_name': subject_perf.subject_name,
                    'passed': subject_perf.passed,
                    'registered': subject_perf.registered
                })
            
            # Sort each subject's performances by GPA (lower is better in NECTA)
            for subject_code, performances in subject_rankings.items():
                performances.sort(key=lambda x: x['gpa'])
            
            # Enhance subject performances with ranking data
            enhanced_subject_performances = []
            for subject in subject_performances:
                subject_code = subject.subject_code
                if subject_code in subject_rankings:
                    # Find this school's position in the ranking
                    ranked_performances = subject_rankings[subject_code]
                    
                    # Find this school's rank
                    school_rank = None
                    for rank, perf in enumerate(ranked_performances, 1):
                        if perf['school_id'] == school.id:
                            school_rank = rank
                            break
                    
                    if school_rank is not None:
                        total_schools_offering = len(ranked_performances)
                        
                        # Handle special case where only one school offers the subject
                        if total_schools_offering == 1:
                            percentile = 100.0  # Only school is automatically top
                            performance_label = "Only School"
                        else:
                            percentile = ((total_schools_offering - school_rank) / total_schools_offering * 100) if total_schools_offering > 0 else 0
                            
                            # Determine performance label
                            if school_rank == 1:
                                performance_label = "🥇 Top"
                            elif school_rank == 2:
                                performance_label = "🥈 2nd"
                            elif school_rank == 3:
                                performance_label = "🥉 3rd"
                            elif school_rank <= 10:
                                performance_label = "Top 10"
                            elif school_rank <= 50:
                                performance_label = "Top 50"
                            elif school_rank <= 100:
                                performance_label = "Top 100"
                            else:
                                performance_label = f"Rank {school_rank}"
                        
                        enhanced_subject_performances.append({
                            'subject': subject,
                            'subject_rank': school_rank,
                            'total_schools_offering': total_schools_offering,
                            'percentile': percentile,
                            'performance_label': performance_label,
                            'top_performer_gpa': ranked_performances[0]['gpa'] if ranked_performances else None,
                            'national_avg_gpa': sum(p['gpa'] for p in ranked_performances) / total_schools_offering if total_schools_offering > 0 else 0
                        })
            
            # Sort by subject rank (best ranked subjects first)
            enhanced_subject_performances.sort(key=lambda x: x['subject_rank'])
            subject_performances = enhanced_subject_performances
        
        # Parse subjects for each student and prepare data for JavaScript (grade distribution)
        subject_data = {}
        for student in student_results:
            # Parse the subject string into a list of (subject, grade) tuples
            student.subjects_list = []
            subject_string = student.subjects
            
            # Try different splitting patterns
            if '   ' in subject_string:  # Triple spaces
                subject_pairs = subject_string.split('   ')
            elif '  ' in subject_string:  # Double spaces
                subject_pairs = subject_string.split('  ')
            else:  # Single spaces with regex for "SUBJ - 'GRADE'"
                subject_pairs = re.findall(r'([A-Za-z\s]+)\s+-\s+\'([A-FS0-9])\'', subject_string)
                if subject_pairs:
                    student.subjects_list = [(subject.strip(), grade) for subject, grade in subject_pairs]
                    for subject, grade in student.subjects_list:
                        if subject not in subject_data:
                            subject_data[subject] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subject]:
                            subject_data[subject][grade] += 1
                            subject_data[subject]['total'] += 1
                    continue
            
            for pair in subject_pairs:
                if pair.strip():
                    parts = pair.split(' - ')
                    if len(parts) == 2:
                        subject = parts[0].strip()
                        grade = parts[1].strip().replace("'", "").replace('"', '')
                        student.subjects_list.append((subject, grade))
                        if subject not in subject_data:
                            subject_data[subject] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subject]:
                            subject_data[subject][grade] += 1
                            subject_data[subject]['total'] += 1
                    elif len(parts) > 2:
                        # Handle cases where subject names contain dashes
                        subject = ' - '.join(parts[:-1]).strip()
                        grade = parts[-1].strip().replace("'", "").replace('"', '')
                        student.subjects_list.append((subject, grade))
                        if subject not in subject_data:
                            subject_data[subject] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subject]:
                            subject_data[subject][grade] += 1
                            subject_data[subject]['total'] += 1
        
        # Convert subject_data to a format that can be passed to JavaScript
        subject_data_for_js = subject_data

    context = {
        'school': school,
        'results': results,
        'student_results': student_results,
        'latest_year': latest_year,
        'latest_exam': latest_exam,
        'subject_data_json': json.dumps(subject_data_for_js),
        'subject_performances': subject_performances,
        'school_ranking': school_ranking,
        'total_schools_in_exam': total_schools_in_exam,
    }
    return render(request, "school_detail.html", context)

def region_rankings(request, exam_type, year, region):
    # Get ranked schools for a specific region
    results = ExamResult.objects.filter(
        exam=exam_type.upper(), 
        year=year,
        school__region__iexact=region,
        gpa__gt=0
    ).select_related('school').order_by("gpa", "-total")
    
    # Add ranking position to each result
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'gpa': result.gpa,
            'division1': result.division1,
            'division2': result.division2,
            'division3': result.division3,
            'division4': result.division4,
            'division0': result.division0,
            'total': result.total,
        })
    
    context = {
        'results': ranked_results,
        'exam_type': exam_type,
        'year': year,
        'region': region,
        'regions': list(School.objects.values_list('region', flat=True).distinct()
                       .exclude(region='Unknown').exclude(region__isnull=True).order_by('region')),
    }
    
    return render(request, "region_rankings.html", context)