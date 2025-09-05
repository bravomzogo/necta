# app/admin.py
from django.contrib import admin
from .models import School, ExamResult,  StudentResult


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
    list_filter = ("exam", "year")
    search_fields = ("school__name", "school__code")
    ordering = ("-year", "exam", "gpa")





@admin.register(StudentResult)
class StudentResultAdmin(admin.ModelAdmin):
    list_display = (
        "candidate_number",
        "sex",
        "division",
        "aggregate_score",
        "exam_result",
    )
    list_filter = ("sex", "division", "exam_result__exam", "exam_result__year")
    search_fields = ("candidate_number", "subjects")
