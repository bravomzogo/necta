from .models import ExamResult

def get_ranked_schools(exam_type: str, year: int):
    # Lower GPA ranks higher (closer to 1.0 is best for NECTA)
    return ExamResult.objects.filter(
        exam=exam_type.upper(), 
        year=year
    ).select_related('school').order_by("gpa", "-total")