from src.models import NewsCategory

CATEGORIES_LANG_MAP = {
    NewsCategory.LOCAL_NEWS: {
        "en": "Local News",
        "hi": "स्थानीय समाचार",
        "mr": "स्थानिक बातम्या",
    },
    NewsCategory.INDIA: {
        "en": "India",
        "hi": "भारत",
        "mr": "भारत",
    },
    NewsCategory.WORLD: {
        "en": "World",
        "hi": "विश्व",
        "mr": "विश्व",
    },
    NewsCategory.POLITICS: {
        "en": "Politics",
        "hi": "राजनीति",
        "mr": "राजकारण",
    },
    NewsCategory.SPORTS: {
        "en": "Sports",
        "hi": "खेलकूद",
        "mr": "क्रीडा",
    },
    NewsCategory.ENTERTAINMENT: {
        "en": "Entertainment",
        "hi": "मनोरंजन",
        "mr": "मनोरंजन",
    },
    NewsCategory.CRIME: {
        "en": "Crime",
        "hi": "अपराध",
        "mr": "गुन्हा",
    },
    NewsCategory.BUSINESS: {
        "en": "Business",
        "hi": "व्यापार",
        "mr": "व्यवसाय",
    },
    NewsCategory.CIVIC_ISSUES: {
        "en": "Civic Issues",
        "hi": "नागरिक मुद्दे",
        "mr": "नागरी मुद्दे",
    },
    NewsCategory.TECHNOLOGY: {
        "en": "Technology",
        "hi": "प्रौद्योगिकी",
        "mr": "तंत्रज्ञान",
    },
    NewsCategory.ENVIRONMENT: {
        "en": "Environment",
        "hi": "पर्यावरण",
        "mr": "पर्यावरण",
    },
    NewsCategory.CULTURE: {
        "en": "Culture",
        "hi": "संस्कृति",
        "mr": "संस्कृती",
    },
    NewsCategory.GENERAL: {
        "en": "General",
        "hi": "सामान्य",
        "mr": "सामान्य",
    },
}

def get_category_name(category: str, lang: str = 'mr') -> str:
    return CATEGORIES_LANG_MAP.get(category, {}).get(lang, "")