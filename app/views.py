from django.shortcuts import render
from django.db.models import Sum, Avg, Count, Q
from .models import ExamResult
from .services import get_ranked_schools

def school_rankings(request, exam_type, year):
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
    
    context = {
        'results': results,
        'exam_type': exam_type,
        'year': year,
        'total_schools': total_schools,
        'total_students': total_students,
        'avg_gpa_all': round(avg_gpa_all, 2),
        'best_gpa': best_gpa,
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
    return render(request, "home.html")