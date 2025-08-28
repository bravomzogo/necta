from django.contrib import admin
from .models import School, ExamResult

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('school', 'exam', 'year', 'total', 'average_score')
    list_filter = ('exam', 'year')
    search_fields = ('school__name', 'school__code')
    ordering = ('-year', '-average_score')
