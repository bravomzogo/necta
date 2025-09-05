from django.db import models

class School(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=100, default="Unknown")

    def __str__(self):
        return f"{self.code} - {self.name} ({self.region})"


class ExamResult(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="results")
    exam = models.CharField(max_length=10)   # "CSEE" or "ACSEE"
    year = models.IntegerField()

    division1 = models.IntegerField(default=0)
    division2 = models.IntegerField(default=0)
    division3 = models.IntegerField(default=0)
    division4 = models.IntegerField(default=0)
    division0 = models.IntegerField(default=0)  # Division 0 (fail/absent)

    total = models.IntegerField(default=0)
    gpa = models.FloatField(default=0.0)  # Lower is better (closer to 1.0 is best)

    class Meta:
        unique_together = ("school", "exam", "year")
        ordering = ["gpa", "-total"]  # Order by GPA (ascending) then by total students (descending)

    def __str__(self):
        return f"{self.school.name} ({self.exam} {self.year}) - GPA: {self.gpa:.2f}"





class StudentResult(models.Model):
    exam_result = models.ForeignKey(ExamResult, on_delete=models.CASCADE, related_name="student_results")
    candidate_number = models.CharField(max_length=20)
    sex = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')])
    aggregate_score = models.CharField(max_length=10)
    division = models.CharField(max_length=5)
    subjects = models.TextField()  # Store as JSON string or comma-separated values

    class Meta:
        unique_together = ("exam_result", "candidate_number")
        
    def __str__(self):
        return f"{self.candidate_number} - {self.exam_result}"