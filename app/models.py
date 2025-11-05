# app/models.py
from django.db import models

class School(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=100, default="Unknown")
    district = models.CharField(max_length=100, default="Unknown")
    council = models.CharField(max_length=100, default="Unknown")
    school_type = models.CharField(max_length=50, default="Primary")  # Primary or Secondary
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class ExamResult(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    exam = models.CharField(max_length=10)  # CSEE, ACSEE, or PSLE
    year = models.IntegerField()
    
    # For secondary schools (CSEE/ACSEE)
    division1 = models.IntegerField(default=0)
    division2 = models.IntegerField(default=0)
    division3 = models.IntegerField(default=0)
    division4 = models.IntegerField(default=0)
    division0 = models.IntegerField(default=0)
    gpa = models.FloatField(null=True, blank=True)
    
    # For primary schools (PSLE)
    grade_a = models.IntegerField(default=0)
    grade_b = models.IntegerField(default=0)
    grade_c = models.IntegerField(default=0)
    grade_d = models.IntegerField(default=0)
    grade_e = models.IntegerField(default=0)
    grade_f = models.IntegerField(default=0)
    average_score = models.FloatField(null=True, blank=True)  # Wastani wa shule
    performance_level = models.CharField(max_length=50, blank=True)  # Daraja A (Bora), etc.
    
    total = models.IntegerField(default=0)

    class Meta:
        unique_together = ('school', 'exam', 'year')

    def __str__(self):
        return f"{self.school.code} - {self.exam} {self.year}"

class SubjectPerformance(models.Model):
    exam_result = models.ForeignKey(ExamResult, on_delete=models.CASCADE, related_name='subject_performances')
    subject_code = models.CharField(max_length=10)
    subject_name = models.CharField(max_length=100)
    
    # Common fields for both PSLE and secondary
    registered = models.IntegerField(default=0)
    sat = models.IntegerField(default=0)
    no_ca = models.IntegerField(default=0)
    withheld = models.IntegerField(default=0)
    clean = models.IntegerField(default=0)
    passed = models.IntegerField(default=0)
    
    # For secondary schools (CSEE/ACSEE) - kept unchanged
    gpa = models.FloatField(null=True, blank=True)
    competency_level = models.CharField(max_length=50, blank=True)
    
    # For PSLE subjects - additional fields
    average_score = models.FloatField(null=True, blank=True)  # Wastani wa alama (/50)
    proficiency_group = models.CharField(max_length=50, blank=True)  # Kundi la Umahiri

    class Meta:
        unique_together = ('exam_result', 'subject_code')

    def __str__(self):
        return f"{self.exam_result} - {self.subject_name}"

    @property
    def is_psle_subject(self):
        """Check if this subject belongs to a PSLE exam"""
        return self.exam_result.exam == 'PSLE'
    
    @property
    def pass_rate(self):
        """Calculate pass rate percentage"""
        if self.registered > 0:
            return (self.passed / self.registered) * 100
        return 0
    
    @property
    def display_score(self):
        """Display appropriate score based on exam type"""
        if self.is_psle_subject:
            return self.average_score  # PSLE uses average score out of 50
        else:
            return self.gpa  # Secondary uses GPA

class StudentResult(models.Model):
    exam_result = models.ForeignKey(ExamResult, on_delete=models.CASCADE)
    candidate_number = models.CharField(max_length=20)
    prem_number = models.CharField(max_length=20, blank=True)  # For PSLE
    sex = models.CharField(max_length=1)
    aggregate_score = models.CharField(max_length=10)
    division = models.CharField(max_length=5)
    subjects = models.TextField()
    average_grade = models.CharField(max_length=5, blank=True)  # For PSLE

    class Meta:
        unique_together = ('exam_result', 'candidate_number')

    def __str__(self):
        return f"{self.candidate_number} - {self.exam_result}"