# app/admin.py
from django.contrib import admin
from .models import School, ExamResult

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
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
