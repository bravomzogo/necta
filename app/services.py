# app/services.py
from .models import ExamResult

def get_ranked_schools(exam_type: str, year: int):
    # Lower average division ranks higher (1 is best)
    return ExamResult.objects.filter(
        exam=exam_type.upper(), 
        year=year
    ).select_related('school').order_by("-average_score", "-total")