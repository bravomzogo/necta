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