from enum import Enum

class NewsCategory(str, Enum):
    LOCAL_NEWS = "Local News"
    INDIA = "India"
    WORLD = "World"
    POLITICS = "Politics"
    SPORTS = "Sports"
    ENTERTAINMENT = "Entertainment"
    CRIME = "Crime"
    BUSINESS = "Business"
    CIVIC_ISSUES = "Civic Issues"
    TECHNOLOGY = "Technology"
    ENVIRONMENT = "Environment"
    CULTURE = "Culture"

def get_category_dep(category: str | None):
    if category is None:
        return None
    

