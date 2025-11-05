# app/admin.py
from django.contrib import admin
from .models import School, ExamResult, SubjectPerformance, StudentResult

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'region', 'district', 'council', 'school_type']
    list_filter = ['school_type', 'region', 'district']
    search_fields = ['code', 'name', 'region', 'district']
    list_per_page = 50

class SubjectPerformanceInline(admin.TabularInline):
    model = SubjectPerformance
    extra = 0
    fields = ['subject_code', 'subject_name', 'registered', 'passed', 'average_score', 'gpa', 'proficiency_group']
    readonly_fields = ['subject_code', 'subject_name']
    
    def get_fields(self, request, obj=None):
        # Show PSLE fields for PSLE exams, secondary fields for others
        if obj and obj.exam == 'PSLE':
            return ['subject_code', 'subject_name', 'registered', 'sat', 'passed', 'average_score', 'proficiency_group']
        else:
            return ['subject_code', 'subject_name', 'registered', 'sat', 'passed', 'gpa', 'competency_level']
    
    def has_add_permission(self, request, obj):
        return False

class StudentResultInline(admin.TabularInline):
    model = StudentResult
    extra = 0
    fields = ['candidate_number', 'prem_number', 'sex', 'average_grade', 'division']
    readonly_fields = ['candidate_number', 'prem_number', 'sex', 'average_grade', 'division']
    
    def get_fields(self, request, obj=None):
        # Show PSLE-specific fields for PSLE exams
        if obj and obj.exam == 'PSLE':
            return ['candidate_number', 'prem_number', 'sex', 'average_grade']
        else:
            return ['candidate_number', 'sex', 'division', 'aggregate_score']
    
    def has_add_permission(self, request, obj):
        return False

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ['school', 'exam', 'year', 'average_score', 'gpa', 'total', 'performance_level']
    list_filter = ['exam', 'year', 'school__region']
    search_fields = ['school__code', 'school__name', 'school__region']
    readonly_fields = ['school', 'exam', 'year']
    inlines = [SubjectPerformanceInline, StudentResultInline]
    
    def get_list_display(self, request):
        # Show appropriate fields based on exam type in list view
        base_fields = ['school', 'exam', 'year', 'total']
        
        # Check if we're filtering by exam type
        exam_filter = request.GET.get('exam__exact', '')
        if exam_filter == 'PSLE':
            return base_fields + ['average_score', 'performance_level']
        else:
            return base_fields + ['gpa', 'division1']
    
    def get_fieldsets(self, request, obj=None):
        # Dynamic fieldsets based on exam type
        if obj and obj.exam == 'PSLE':
            return [
                ('Basic Information', {
                    'fields': ['school', 'exam', 'year', 'total']
                }),
                ('PSLE Performance', {
                    'fields': [
                        ('grade_a', 'grade_b', 'grade_c'),
                        ('grade_d', 'grade_e', 'grade_f'),
                        'average_score',
                        'performance_level'
                    ]
                })
            ]
        else:
            return [
                ('Basic Information', {
                    'fields': ['school', 'exam', 'year', 'total']
                }),
                ('Secondary School Performance', {
                    'fields': [
                        ('division1', 'division2', 'division3'),
                        ('division4', 'division0'),
                        'gpa'
                    ]
                })
            ]
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return ['school', 'exam', 'year']
        return []

@admin.register(SubjectPerformance)
class SubjectPerformanceAdmin(admin.ModelAdmin):
    list_display = ['exam_result', 'subject_name', 'registered', 'passed', 'display_score', 'pass_rate']
    list_filter = ['exam_result__exam', 'exam_result__year']
    search_fields = ['subject_name', 'exam_result__school__name']
    readonly_fields = ['exam_result', 'subject_code', 'subject_name']
    
    def display_score(self, obj):
        """Display appropriate score based on exam type"""
        if obj.is_psle_subject:
            return f"{obj.average_score}/50" if obj.average_score else "-"
        else:
            return obj.gpa if obj.gpa else "-"
    display_score.short_description = 'Score'
    
    def pass_rate(self, obj):
        """Calculate and display pass rate"""
        if obj.registered > 0:
            return f"{(obj.passed / obj.registered) * 100:.1f}%"
        return "0%"
    pass_rate.short_description = 'Pass Rate'
    
    def get_list_display(self, request):
        # Dynamic list display based on exam type filter
        exam_filter = request.GET.get('exam_result__exam__exact', '')
        base_fields = ['exam_result', 'subject_name', 'registered', 'passed', 'pass_rate']
        
        if exam_filter == 'PSLE':
            return base_fields + ['average_score']
        else:
            return base_fields + ['gpa']
    
    def get_fieldsets(self, request, obj=None):
        if obj and obj.is_psle_subject:
            return [
                ('Basic Information', {
                    'fields': ['exam_result', 'subject_code', 'subject_name']
                }),
                ('PSLE Subject Performance', {
                    'fields': [
                        ('registered', 'sat', 'passed'),
                        ('no_ca', 'withheld', 'clean'),
                        'average_score',
                        'proficiency_group'
                    ]
                })
            ]
        else:
            return [
                ('Basic Information', {
                    'fields': ['exam_result', 'subject_code', 'subject_name']
                }),
                ('Subject Performance', {
                    'fields': [
                        ('registered', 'sat', 'passed'),
                        ('no_ca', 'withheld', 'clean'),
                        'gpa',
                        'competency_level'
                    ]
                })
            ]

@admin.register(StudentResult)
class StudentResultAdmin(admin.ModelAdmin):
    list_display = ['exam_result', 'candidate_number', 'sex', 'display_grade_division']
    list_filter = ['exam_result__exam', 'exam_result__year', 'sex']
    search_fields = ['candidate_number', 'prem_number', 'exam_result__school__name']
    readonly_fields = ['exam_result', 'candidate_number', 'prem_number']
    
    def display_grade_division(self, obj):
        """Display appropriate result based on exam type"""
        if obj.exam_result.exam == 'PSLE':
            return obj.average_grade if obj.average_grade else "-"
        else:
            return obj.division if obj.division else "-"
    display_grade_division.short_description = 'Grade/Division'
    
    def get_list_display(self, request):
        # Dynamic list display based on exam type filter
        exam_filter = request.GET.get('exam_result__exam__exact', '')
        base_fields = ['exam_result', 'candidate_number', 'sex']
        
        if exam_filter == 'PSLE':
            return base_fields + ['average_grade', 'prem_number']
        else:
            return base_fields + ['division', 'aggregate_score']
    
    def get_fieldsets(self, request, obj=None):
        if obj and obj.exam_result.exam == 'PSLE':
            return [
                ('Basic Information', {
                    'fields': ['exam_result', 'candidate_number', 'prem_number', 'sex']
                }),
                ('PSLE Results', {
                    'fields': ['average_grade', 'subjects']
                })
            ]
        else:
            return [
                ('Basic Information', {
                    'fields': ['exam_result', 'candidate_number', 'sex']
                }),
                ('Secondary Results', {
                    'fields': ['division', 'aggregate_score', 'subjects']
                })
            ]

# Customize admin site header
admin.site.site_header = "NECTA Results Administration"
admin.site.site_title = "NECTA Results Admin"
admin.site.index_title = "Welcome to NECTA Results Administration"