# app/models.py
from django.db import models

class School(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=100, default="Unknown")

    def __str__(self):
        return f"{self.code} - {self.name}"

class ExamResult(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    exam = models.CharField(max_length=10)  # CSEE or ACSEE
    year = models.IntegerField()
    division1 = models.IntegerField(default=0)
    division2 = models.IntegerField(default=0)
    division3 = models.IntegerField(default=0)
    division4 = models.IntegerField(default=0)
    division0 = models.IntegerField(default=0)
    total = models.IntegerField(default=0)
    gpa = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('school', 'exam', 'year')

    def __str__(self):
        return f"{self.school.code} - {self.exam} {self.year}"

class SubjectPerformance(models.Model):
    exam_result = models.ForeignKey(ExamResult, on_delete=models.CASCADE, related_name='subject_performances')
    subject_code = models.CharField(max_length=10)
    subject_name = models.CharField(max_length=100)
    registered = models.IntegerField(default=0)
    sat = models.IntegerField(default=0)
    no_ca = models.IntegerField(default=0)
    withheld = models.IntegerField(default=0)
    clean = models.IntegerField(default=0)
    passed = models.IntegerField(default=0)
    gpa = models.FloatField(null=True, blank=True)
    competency_level = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = ('exam_result', 'subject_code')

    def __str__(self):
        return f"{self.exam_result} - {self.subject_name} (GPA: {self.gpa})"

class StudentResult(models.Model):
    exam_result = models.ForeignKey(ExamResult, on_delete=models.CASCADE)
    candidate_number = models.CharField(max_length=20)
    sex = models.CharField(max_length=1)
    aggregate_score = models.CharField(max_length=10)
    division = models.CharField(max_length=5)
    subjects = models.TextField()

    class Meta:
        unique_together = ('exam_result', 'candidate_number')

    def __str__(self):
        return f"{self.candidate_number} - {self.exam_result}"