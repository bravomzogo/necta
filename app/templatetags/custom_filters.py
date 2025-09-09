# app/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter(name='split')
def split(value, key):
    """
    Returns the value turned into a list.
    """
    return value.split(key)

@register.filter(name='trim')
def trim(value):
    """
    Trims whitespace from both ends of a string.
    """
    return value.strip()

@register.filter(name='cut')
def cut(value, arg):
    """
    Removes all occurrences of arg from the given string.
    """
    return value.replace(arg, '')


# app/templatetags/custom_filters.py

register = template.Library()

@register.filter
def div(value, arg):
    """Divide value by arg"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except ValueError:
        return 0


register = template.Library()

@register.filter
def is_numeric(value):
    """Check if a value is numeric"""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False