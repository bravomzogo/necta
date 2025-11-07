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

import json
import re
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Avg, Count, Q
from .models import ExamResult, School, StudentResult, SubjectPerformance

def school_detail(request, school_id):
    # Get school details
    school = get_object_or_404(School, id=school_id)
    
    # Get year and exam_type from query parameters
    year_str = request.GET.get('year')
    exam_type = request.GET.get('exam_type', 'ACSEE').upper()  # Default to ACSEE if not provided
    
    # Get all results for the school (for history table)
    results = ExamResult.objects.filter(school=school).order_by('-year', 'exam')
    
    # Initialize variables
    student_results = []
    subject_data_for_js = {}
    subject_performances = []
    school_ranking = None
    total_schools_in_exam = 0
    selected_result = None
    latest_year = None
    latest_exam = None
    selected_year = None

    # Parse year
    if year_str:
        try:
            selected_year = int(year_str)
        except ValueError:
            selected_year = None  # Invalid year

    # Filter for selected_result
    if selected_year and exam_type:
        if exam_type.lower() == 'all':
            # For 'all', get first result for the year (any exam)
            selected_result = results.filter(year=selected_year).first()
        else:
            # Filter by specific exam
            selected_result = results.filter(year=selected_year, exam=exam_type).first()
    
    # Fallback if no selected_result
    if not selected_result and results.exists():
        selected_result = results.first()  # Latest available

    if selected_result:
        latest_year = selected_result.year
        latest_exam = selected_result.exam

        print(f"DEBUG: Selected result - Year: {latest_year}, Exam: {latest_exam}, School: {school.name}")  # Debug

        # Get school's ranking position for the selected exam/year
        ranked_schools = ExamResult.objects.filter(
            exam=latest_exam,
            year=latest_year,
            gpa__gt=0
        ).select_related('school').order_by('gpa', '-total')
        
        total_schools_in_exam = ranked_schools.count()
        print(f"DEBUG: Total schools in exam: {total_schools_in_exam}")  # Debug
        
        # Find ranking
        ranked_list = list(ranked_schools)
        for rank, result in enumerate(ranked_list, start=1):
            if result.school.id == school.id:
                school_ranking = rank
                break
        
        # Get student results
        student_results = StudentResult.objects.filter(exam_result=selected_result).order_by('candidate_number')
        print(f"DEBUG: Student results count: {student_results.count()}")  # Debug
        
        # Get subject performances for this school
        subject_performances = list(SubjectPerformance.objects.filter(exam_result=selected_result).order_by('gpa'))
        print(f"DEBUG: School subject performances count: {len(subject_performances)}")  # Debug
        
        if subject_performances:
            # Get all subject performances for national comparison
            all_subject_performances = list(SubjectPerformance.objects.filter(
                exam_result__exam=latest_exam,
                exam_result__year=latest_year,
                gpa__isnull=False
            ).select_related('exam_result__school'))
            print(f"DEBUG: All subject performances count: {len(all_subject_performances)}")  # Debug
            
            # Group by subject code
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
                    'passed': getattr(subject_perf, 'passed', 0),  # Assume field exists
                    'registered': getattr(subject_perf, 'registered', 0)  # Assume field exists
                })
            
            # Sort each subject by GPA (lower better)
            for subject_code, performances in subject_rankings.items():
                performances.sort(key=lambda x: x['gpa'])
            
            # Enhance school's subjects with rankings
            enhanced_subject_performances = []
            for subject in subject_performances:
                subject_code = subject.subject_code
                if subject_code in subject_rankings:
                    ranked_performances = subject_rankings[subject_code]
                    
                    # Find school's rank
                    school_rank = None
                    for rank, perf in enumerate(ranked_performances, 1):
                        if perf['school_id'] == school.id:
                            school_rank = rank
                            break
                    
                    if school_rank is not None:
                        total_schools_offering = len(ranked_performances)
                        
                        if total_schools_offering == 1:
                            percentile = 100.0
                            performance_label = "Only School"
                        else:
                            percentile = max(0, ((total_schools_offering - school_rank) / (total_schools_offering - 1)) * 100)  # Adjusted percentile (exclude self for better calc)
                            
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
                            'percentile': round(percentile, 1),
                            'performance_label': performance_label,
                            'top_performer_gpa': ranked_performances[0]['gpa'] if ranked_performances else subject.gpa,
                            'national_avg_gpa': round(sum(p['gpa'] for p in ranked_performances) / total_schools_offering, 2) if total_schools_offering > 0 else subject.gpa
                        })
                        print(f"DEBUG: Enhanced {subject.subject_code} - Rank: {school_rank}, Schools: {total_schools_offering}")  # Debug
            
            # Fix: Sort without mutating to None
            subject_performances = sorted(enhanced_subject_performances, key=lambda x: x['subject_rank'])
            print(f"DEBUG: Final subject_performances count: {len(subject_performances)}")  # Debug

        # Parse subjects for JS charts (unchanged)
        subject_data = {}
        for student in student_results:
            student.subjects_list = []  # Ensure this is set
            subject_string = getattr(student, 'subjects', '')
            
            # Parsing logic (unchanged, but added safety)
            if not subject_string:
                continue
                
            if '   ' in subject_string:
                subject_pairs = [p.strip() for p in subject_string.split('   ') if p.strip()]
            elif '  ' in subject_string:
                subject_pairs = [p.strip() for p in subject_string.split('  ') if p.strip()]
            else:
                import re
                subject_pairs = re.findall(r'([A-Za-z\s]+?)\s*-\s*\'?([A-FS])\'?', subject_string)
                if subject_pairs:
                    student.subjects_list = [(subject.strip(), grade) for subject, grade in subject_pairs]
                    for subj_name, grade in student.subjects_list:
                        if subj_name not in subject_data:
                            subject_data[subj_name] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subj_name]:
                            subject_data[subj_name][grade] += 1
                            subject_data[subj_name]['total'] += 1
                    continue
            
            for pair in subject_pairs:
                parts = pair.split(' - ')
                if len(parts) >= 2:
                    subject = ' - '.join(parts[:-1]).strip()
                    grade = parts[-1].strip().replace("'", "").replace('"', '').upper()[:1]
                    if grade in 'ABCDEF S':
                        student.subjects_list.append((subject, grade))
                        if subject not in subject_data:
                            subject_data[subject] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subject]:
                            subject_data[subject][grade] += 1
                            subject_data[subject]['total'] += 1
        
        subject_data_for_js = subject_data
        print(f"DEBUG: Subject data keys: {list(subject_data.keys())}")  # Debug

    # Context (add selected vars)
    context = {
        'school': school,
        'results': results,
        'student_results': student_results,
        'latest_year': latest_year,
        'latest_exam': latest_exam,
        'selected_year': selected_year,
        'selected_exam_type': exam_type,
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







# app/views.py
from django.shortcuts import render
from django.db.models import Avg, Count, Sum
from django.core.paginator import Paginator
from .models import ExamResult, School

from django.core.paginator import Paginator

def psle_rankings(request, year):
    """PSLE school rankings by average score"""
    # Get PSLE results ordered by average score (higher is better)
    results = ExamResult.objects.filter(
        exam='PSLE', 
        year=year,
        average_score__isnull=False
    ).select_related('school').order_by('-average_score')
    
    # Get unique regions for filter
    all_regions = list(School.objects.filter(
        school_type='Primary'
    ).values_list('region', flat=True).distinct()
    .exclude(region='Unknown').exclude(region__isnull=True).order_by('region'))
    
    # Filter regions to only show uppercase (no duplicates)
    regions = [region for region in all_regions if region == region.upper()]
    
    # Get unique districts for filter
    districts = list(School.objects.filter(
        school_type='Primary'
    ).values_list('district', flat=True).distinct()
    .exclude(district='Unknown').exclude(district__isnull=True).order_by('district'))
    
    # Add ranking position to each result
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'average_score': result.average_score,
            'performance_level': result.performance_level,
            'grade_a': result.grade_a or 0,
            'grade_b': result.grade_b or 0,
            'grade_c': result.grade_c or 0,
            'grade_d': result.grade_d or 0,
            'grade_e': result.grade_e or 0,
            'total': result.total or 0,
        })
    
    # Pagination - 100 schools per page
    paginator = Paginator(ranked_results, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics (calculate from all results)
    total_schools = results.count()
    total_students = results.aggregate(total=Sum('total'))['total'] or 0
    avg_score = results.aggregate(avg=Avg('average_score'))['avg'] or 0
    best_score = ranked_results[0]['average_score'] if ranked_results else 0
    
    context = {
        'page_obj': page_obj,
        'results': page_obj,
        'regions': regions,
        'districts': districts,
        'year': year,
        'exam_type': 'PSLE',
        'total_schools': total_schools,
        'total_students': total_students,
        'avg_score': round(avg_score, 2),
        'best_score': round(best_score, 2),
    }
    
    return render(request, "psle_rankings.html", context)

def psle_region_rankings(request, year, region):
    """PSLE rankings by region"""
    results = ExamResult.objects.filter(
        exam='PSLE', 
        year=year,
        average_score__isnull=False,
        school__region__iexact=region
    ).select_related('school').order_by('-average_score')
    
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'average_score': result.average_score,
            'performance_level': result.performance_level,
            'total': result.total or 0,
        })
    
    context = {
        'results': ranked_results,
        'year': year,
        'region': region,
        'exam_type': 'PSLE',
        'regions': School.objects.filter(school_type='Primary').values_list('region', flat=True).distinct().order_by('region'),
    }
    
    return render(request, "psle_region_rankings.html", context)

def psle_district_rankings(request, year, region, district):
    """PSLE rankings by district"""
    results = ExamResult.objects.filter(
        exam='PSLE', 
        year=year,
        average_score__isnull=False,
        school__region__iexact=region,
        school__district__iexact=district
    ).select_related('school').order_by('-average_score')
    
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'average_score': result.average_score,
            'performance_level': result.performance_level,
            'total': result.total,
        })
    
    context = {
        'results': ranked_results,
        'year': year,
        'region': region,
        'district': district,
        'districts': School.objects.filter(
            school_type='Primary', 
            region__iexact=region
        ).values_list('district', flat=True).distinct().order_by('district'),
    }
    
    return render(request, "psle_district_rankings.html", context)

def psle_council_rankings(request, year, region, district, council):
    """PSLE rankings by council"""
    results = ExamResult.objects.filter(
        exam='PSLE', 
        year=year,
        average_score__isnull=False,
        school__region__iexact=region,
        school__district__iexact=district,
        school__council__iexact=council
    ).select_related('school').order_by('-average_score')
    
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': result.school,
            'average_score': result.average_score,
            'performance_level': result.performance_level,
            'total': result.total,
        })
    
    context = {
        'results': ranked_results,
        'year': year,
        'region': region,
        'district': district,
        'council': council,
        'councils': School.objects.filter(
            school_type='Primary', 
            region__iexact=region,
            district__iexact=district
        ).values_list('council', flat=True).distinct().order_by('council'),
    }
    
    return render(request, "psle_council_rankings.html", context)





# app/views.py
def psle_school_detail(request, school_id):
    """Dedicated PSLE school detail page with subject rankings"""
    # Get school details
    school = get_object_or_404(School, id=school_id)
    
    # Get year from query parameters
    year_str = request.GET.get('year')
    
    # Get all PSLE results for the school (for history table)
    results = ExamResult.objects.filter(school=school, exam='PSLE').order_by('-year')
    
    # Initialize variables
    selected_year = None
    selected_result = None
    latest_year = None
    subject_performances = []
    
    # Parse year
    if year_str:
        try:
            selected_year = int(year_str)
        except ValueError:
            selected_year = None

    # Filter for selected_result
    if selected_year:
        selected_result = results.filter(year=selected_year).first()
    
    # Fallback if no selected_result
    if not selected_result and results.exists():
        selected_result = results.first()

    # Get school ranking and subject performances for selected year
    school_ranking = None
    total_schools_in_exam = 0
    
    if selected_result:
        latest_year = selected_result.year
        
        # Get school's ranking position for the selected year
        ranked_schools = ExamResult.objects.filter(
            exam='PSLE',
            year=latest_year,
            average_score__isnull=False
        ).select_related('school').order_by('-average_score')
        
        total_schools_in_exam = ranked_schools.count()
        
        # Find ranking
        ranked_list = list(ranked_schools)
        for rank, result in enumerate(ranked_list, start=1):
            if result.school.id == school.id:
                school_ranking = rank
                break

        # Get subject performances for this school with rankings
        subject_performances = get_psle_subject_rankings(selected_result, school, latest_year)

    # Get performance history for charts
    performance_history = []
    for result in results:
        performance_history.append({
            'year': result.year,
            'average_score': result.average_score,
            'performance_level': result.performance_level,
            'total_students': result.total,
            'grade_a': result.grade_a or 0,
            'grade_b': result.grade_b or 0,
            'grade_c': result.grade_c or 0,
            'grade_d': result.grade_d or 0,
            'grade_e': result.grade_e or 0,
        })

    context = {
        'school': school,
        'results': results,
        'selected_result': selected_result,
        'selected_year': selected_year,
        'latest_year': latest_year,
        'performance_history': performance_history,
        'subject_performances': subject_performances,
        'school_ranking': school_ranking,
        'total_schools_in_exam': total_schools_in_exam,
        'exam_type': 'PSLE',
    }
    return render(request, "psle_school_detail.html", context)


def get_psle_subject_rankings(exam_result, school, year):
    """Get PSLE subject performances with national rankings"""
    # Get this school's subject performances
    school_subjects = SubjectPerformance.objects.filter(
        exam_result=exam_result
    ).order_by('subject_code')
    
    if not school_subjects.exists():
        return []
    
    # Get all subject performances for national comparison
    all_subject_performances = list(SubjectPerformance.objects.filter(
        exam_result__exam='PSLE',
        exam_result__year=year,
        average_score__isnull=False
    ).select_related('exam_result__school'))
    
    # Group by subject code
    subject_rankings = {}
    for subject_perf in all_subject_performances:
        subject_code = subject_perf.subject_code
        if subject_code not in subject_rankings:
            subject_rankings[subject_code] = []
        
        subject_rankings[subject_code].append({
            'school_id': subject_perf.exam_result.school.id,
            'school_name': subject_perf.exam_result.school.name,
            'average_score': subject_perf.average_score,
            'subject_name': subject_perf.subject_name,
            'passed': subject_perf.passed,
            'registered': subject_perf.registered,
            'proficiency_group': subject_perf.proficiency_group
        })
    
    # Sort each subject by average_score (higher is better for PSLE)
    for subject_code, performances in subject_rankings.items():
        performances.sort(key=lambda x: x['average_score'], reverse=True)
    
    # Enhance school's subjects with rankings
    enhanced_subject_performances = []
    for subject in school_subjects:
        subject_code = subject.subject_code
        if subject_code in subject_rankings:
            ranked_performances = subject_rankings[subject_code]
            
            # Find school's rank
            school_rank = None
            for rank, perf in enumerate(ranked_performances, 1):
                if perf['school_id'] == school.id:
                    school_rank = rank
                    break
            
            if school_rank is not None:
                total_schools_offering = len(ranked_performances)
                
                if total_schools_offering == 1:
                    percentile = 100.0
                    performance_label = "Only School"
                else:
                    percentile = ((total_schools_offering - school_rank) / total_schools_offering) * 100
                    
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
                    elif school_rank <= 500:
                        performance_label = "Top 500"
                    else:
                        performance_label = f"Rank {school_rank}"
                
                enhanced_subject_performances.append({
                    'subject': subject,
                    'subject_rank': school_rank,
                    'total_schools_offering': total_schools_offering,
                    'percentile': round(percentile, 1),
                    'performance_label': performance_label,
                    'top_performer_score': ranked_performances[0]['average_score'] if ranked_performances else subject.average_score,
                    'national_avg_score': round(sum(p['average_score'] for p in ranked_performances) / total_schools_offering, 1) if total_schools_offering > 0 else subject.average_score
                })
    
    # Sort by rank (best performing subjects first)
    return sorted(enhanced_subject_performances, key=lambda x: x['subject_rank'])