# app/views.py
from django.shortcuts import render
from django.db.models import Sum, Avg, Count, Q
from .models import ExamResult
from .services import get_ranked_schools

def school_rankings(request, exam_type, year):
    results = get_ranked_schools(exam_type, year)
    
    # Calculate statistics for the charts
    total_schools = results.count()
    total_students = results.aggregate(total=Sum('total'))['total'] or 0
    
    # Only calculate average if we have schools with valid scores
    valid_results = results.exclude(average_score=0)
    avg_score_all = valid_results.aggregate(avg=Avg('average_score'))['avg'] or 0 if valid_results.exists() else 0
    
    top_score = results.first().average_score if results else 0
    
    # Division totals
    division_totals = results.aggregate(
        div1=Sum('division1'),
        div2=Sum('division2'),
        div3=Sum('division3'),
        div4=Sum('division4'),
        div0=Sum('division0')
    )
    
    # Performance distribution - ensure we handle cases where average_score might be None
    score_ranges = {
        '0_1': results.filter(average_score__gte=0, average_score__lt=1).count(),
        '1_2': results.filter(average_score__gte=1, average_score__lt=2).count(),
        '2_3': results.filter(average_score__gte=2, average_score__lt=3).count(),
        '3_4': results.filter(average_score__gte=3, average_score__lte=4).count(),
    }
    
    context = {
        'results': results,
        'exam_type': exam_type,
        'year': year,
        'total_schools': total_schools,
        'total_students': total_students,
        'avg_score_all': avg_score_all,
        'top_score': top_score,
        'division1_total': division_totals['div1'] or 0,
        'division2_total': division_totals['div2'] or 0,
        'division3_total': division_totals['div3'] or 0,
        'division4_total': division_totals['div4'] or 0,
        'division0_total': division_totals['div0'] or 0,
        'score_0_1': score_ranges['0_1'],
        'score_1_2': score_ranges['1_2'],
        'score_2_3': score_ranges['2_3'],
        'score_3_4': score_ranges['3_4'],
    }
    
    return render(request, "rankings.html", context)


def home(request):
    return render(request, "home.html")