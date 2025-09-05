import json
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Avg, Count, Q
from .models import ExamResult, School, StudentResult
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

def school_detail(request, school_id):
    # Get school details and all its exam results
    school = get_object_or_404(School, id=school_id)
    results = ExamResult.objects.filter(school=school).order_by('-year', 'exam')
    
    # Get student results for the latest result
    student_results = []
    latest_year = None
    latest_exam = None
    subject_data_for_js = {}  # Add this to store subject data for JavaScript
    
    if results.exists():
        latest_result = results.first()
        latest_year = latest_result.year
        latest_exam = latest_result.exam
        
        student_results = StudentResult.objects.filter(
            exam_result=latest_result
        ).order_by('candidate_number')
        
        # Parse subjects for each student and prepare data for JavaScript
        subject_data = {}
        
        for student in student_results:
            # Parse the subject string into a list of (subject, grade) tuples
            student.subjects_list = []
            
            # Handle different possible formats in the subject string
            subject_string = student.subjects
            
            # Try different splitting patterns
            if '   ' in subject_string:  # Triple spaces
                subject_pairs = subject_string.split('   ')
            elif '  ' in subject_string:  # Double spaces
                subject_pairs = subject_string.split('  ')
            else:  # Single spaces (try a more sophisticated approach)
                # This regex pattern looks for patterns like "SUBJ - 'GRADE'"
                import re
                subject_pairs = re.findall(r'([A-Za-z\s]+)\s+-\s+\'([A-FS0-9])\'', subject_string)
                # If regex found matches, process them
                if subject_pairs:
                    student.subjects_list = [(subject.strip(), grade) for subject, grade in subject_pairs]
                    # Also add to subject_data for JavaScript
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
                        # Add to subject_data for JavaScript
                        if subject not in subject_data:
                            subject_data[subject] = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'S': 0, 'F': 0, 'total': 0}
                        if grade in subject_data[subject]:
                            subject_data[subject][grade] += 1
                            subject_data[subject]['total'] += 1
                    elif len(parts) > 2:
                        # Handle cases where there might be extra dashes in subject names
                        subject = ' - '.join(parts[:-1]).strip()
                        grade = parts[-1].strip().replace("'", "").replace('"', '')
                        student.subjects_list.append((subject, grade))
                        # Add to subject_data for JavaScript
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
        'subject_data_json': json.dumps(subject_data_for_js),  # Add this line
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