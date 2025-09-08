# app/admin.py
from django.contrib import admin
from .models import School, ExamResult, SubjectPerformance, StudentResult


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region")
    search_fields = ("code", "name", "region")
    ordering = ("code",)


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "exam",
        "year",
        "division1",
        "division2",
        "division3",
        "division4",
        "division0",
        "total",
        "gpa",
    )
    search_fields = ("school__code", "school__name", "exam", "year")
    list_filter = ("exam", "year")
    ordering = ("-year", "exam")


@admin.register(SubjectPerformance)
class SubjectPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "exam_result",
        "subject_code",
        "subject_name",
        "registered",
        "sat",
        "passed",
        "gpa",
        "competency_level",
    )
    search_fields = ("subject_code", "subject_name", "exam_result__school__name")
    list_filter = ("exam_result__exam", "exam_result__year", "subject_name")
    ordering = ("subject_code",)


@admin.register(StudentResult)
class StudentResultAdmin(admin.ModelAdmin):
    list_display = (
        "exam_result",
        "candidate_number",
        "sex",
        "aggregate_score",
        "division",
    )
    search_fields = ("candidate_number", "division", "exam_result__school__name")
    list_filter = ("division", "sex", "exam_result__exam", "exam_result__year")
    ordering = ("candidate_number",)
