"""
Multilingual explanations for pyerror.

`set_language("hi")` or `set_language("es")` wraps SuggestionEngine.get_details
so the translation/why fields come back in the chosen language. Suggestion
text remains in English (with a localized orientation line) — kept honest
about scope rather than badly machine-translating technical guidance.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pyerror.suggestions import SuggestionEngine

_LANGUAGE = "en"
_ORIGINAL: Optional[Callable] = None

# Per-language catalog. Each entry: per-exception type -> {translation, why,
# prefix (added as first suggestion line)}.
_CATALOG: Dict[str, Dict[str, Dict[str, str]]] = {
    "hi": {
        "KeyError": {
            "translation": "आपने डिक्शनरी में एक ऐसी कुंजी (key) तक पहुँचने की कोशिश की जो मौजूद नहीं है।",
            "why": "जिस डिक्शनरी को आपने एक्सेस किया, उसमें यह कुंजी नहीं मिली।",
            "prefix": "नीचे सुझाव देखें — तकनीकी विवरण अंग्रेज़ी में सुरक्षित रखे गए हैं।",
        },
        "NameError": {
            "translation": "आपने एक ऐसा वेरिएबल, फ़ंक्शन या मॉड्यूल नाम इस्तेमाल किया जो अभी तक परिभाषित नहीं किया गया है।",
            "why": "पाइथन को यह नाम कहीं नहीं मिला।",
            "prefix": "नीचे सुझाव देखें — नाम जाँचें और इम्पोर्ट सही करें।",
        },
        "TypeError": {
            "translation": "असंगत डेटा प्रकारों पर एक ऑपरेशन किया गया।",
            "why": "पाइथन इन दो टाइप्स के बीच यह ऑपरेशन स्वचालित रूप से नहीं कर सकता।",
            "prefix": "नीचे सुझाव देखें — वैल्यू को सही टाइप में बदलने पर विचार करें।",
        },
        "ValueError": {
            "translation": "फ़ंक्शन को सही प्रकार का मान मिला, लेकिन वह मान अमान्य है।",
            "why": "पास की गई वैल्यू को फ़ंक्शन प्रोसेस नहीं कर सका।",
            "prefix": "नीचे सुझाव देखें — इनपुट को मान्य करें।",
        },
        "IndexError": {
            "translation": "आपने सूची (list) में एक ऐसे इंडेक्स को एक्सेस किया जो उसकी सीमा से बाहर है।",
            "why": "सूची की लंबाई से बड़ा इंडेक्स माँगा गया।",
            "prefix": "नीचे सुझाव देखें — सूची की लंबाई जाँचें।",
        },
        "AttributeError": {
            "translation": "ऑब्जेक्ट के पास वह एट्रिब्यूट या मेथड नहीं है जिसे आपने एक्सेस किया।",
            "why": "ऑब्जेक्ट के टाइप पर यह नाम मौजूद नहीं है।",
            "prefix": "नीचे सुझाव देखें — स्पेलिंग और ऑब्जेक्ट टाइप जाँचें।",
        },
        "ZeroDivisionError": {
            "translation": "किसी संख्या को शून्य से विभाजित नहीं किया जा सकता।",
            "why": "विभाजन ऑपरेशन में भाजक (divisor) शून्य था।",
            "prefix": "नीचे सुझाव देखें — विभाजन से पहले भाजक की जाँच करें।",
        },
        "ImportError": {
            "translation": "पाइथन निर्दिष्ट मॉड्यूल या नाम को इम्पोर्ट नहीं कर सका।",
            "why": "मॉड्यूल इंस्टॉल नहीं है, या नाम मॉड्यूल में मौजूद नहीं है।",
            "prefix": "नीचे सुझाव देखें — पैकेज इंस्टॉल और इम्पोर्ट नाम जाँचें।",
        },
        "FileNotFoundError": {
            "translation": "जिस फ़ाइल को आपने खोलने की कोशिश की वह उस पथ पर मौजूद नहीं है।",
            "why": "पाइथन को इस पथ पर कोई फ़ाइल नहीं मिली।",
            "prefix": "नीचे सुझाव देखें — पथ और मौजूदा डायरेक्टरी जाँचें।",
        },
        "IndentationError": {
            "translation": "कोड का इंडेंटेशन (खाली जगह) सही नहीं है।",
            "why": "पाइथन कोड ब्लॉक्स की पहचान इंडेंटेशन से करता है।",
            "prefix": "नीचे सुझाव देखें — स्पेस और टैब एक समान रखें।",
        },
        "__default__": {
            "translation": "एक अनपेक्षित त्रुटि हुई।",
            "why": "पाइथन ने आपका कोड चलाते समय यह त्रुटि पकड़ी।",
            "prefix": "नीचे सुझाव देखें।",
        },
    },
    "es": {
        "KeyError": {
            "translation": "Intentaste acceder a una clave que no existe en el diccionario.",
            "why": "La clave indicada no se encontró en el diccionario consultado.",
            "prefix": "Consulta las sugerencias abajo (en inglés).",
        },
        "NameError": {
            "translation": "Usaste un nombre de variable, función o módulo que no está definido.",
            "why": "Python no encontró ninguna definición con ese nombre en el alcance actual.",
            "prefix": "Consulta las sugerencias abajo — revisa imports y typos.",
        },
        "TypeError": {
            "translation": "Una operación se realizó sobre tipos de datos incompatibles.",
            "why": "Python no puede realizar esta operación entre estos dos tipos automáticamente.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "ValueError": {
            "translation": "La función recibió un valor del tipo correcto pero inválido.",
            "why": "El valor no pudo ser procesado por la función.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "IndexError": {
            "translation": "Intentaste acceder a un índice fuera del rango de la lista.",
            "why": "El índice solicitado es mayor o igual a la longitud de la lista.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "AttributeError": {
            "translation": "El objeto no tiene el atributo o método que intentaste usar.",
            "why": "Ese nombre no existe en el tipo del objeto.",
            "prefix": "Consulta las sugerencias abajo — verifica spelling y type().",
        },
        "ZeroDivisionError": {
            "translation": "No se puede dividir un número entre cero.",
            "why": "El divisor en la operación era cero.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "ImportError": {
            "translation": "Python no pudo importar el módulo o nombre solicitado.",
            "why": "El módulo no está instalado o el nombre no existe dentro de él.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "FileNotFoundError": {
            "translation": "El archivo indicado no existe en esa ruta.",
            "why": "Python no encontró ningún archivo en esa ruta.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "IndentationError": {
            "translation": "La indentación del código no es correcta.",
            "why": "Python identifica los bloques de código por su indentación.",
            "prefix": "Consulta las sugerencias abajo.",
        },
        "__default__": {
            "translation": "Ocurrió un error inesperado.",
            "why": "Python detectó este error durante la ejecución.",
            "prefix": "Consulta las sugerencias abajo.",
        },
    },
}


_LABELS: Dict[str, Dict[str, str]] = {
    "en": {"suggestions": "Suggestions", "why": "Why", "example": "Example", "translation": "Explanation"},
    "hi": {"suggestions": "सुझाव", "why": "कारण", "example": "उदाहरण", "translation": "व्याख्या"},
    "es": {"suggestions": "Sugerencias", "why": "Por qué", "example": "Ejemplo", "translation": "Explicación"},
}


def labels() -> Dict[str, str]:
    return dict(_LABELS.get(_LANGUAGE, _LABELS["en"]))


def get_language() -> str:
    return _LANGUAGE


def _translate(details: Dict[str, Any]) -> Dict[str, Any]:
    if _LANGUAGE == "en":
        return details
    lang = _CATALOG.get(_LANGUAGE, {})
    name = details.get("name", "")
    entry = lang.get(name) or lang.get("__default__")
    if not entry:
        return details
    out = dict(details)
    out["translation"] = entry["translation"]
    out["why"] = entry["why"]
    prefix = entry.get("prefix")
    if prefix:
        suggestions = list(details.get("suggestions") or [])
        out["suggestions"] = [prefix] + suggestions
    return out


def set_language(code: str) -> str:
    """Switch the language for translation/why fields. Use `reset_language()` to undo."""
    global _LANGUAGE, _ORIGINAL
    code = (code or "en").lower()
    if code not in _CATALOG and code != "en":
        raise ValueError("Unknown language code '{}'. Available: en, {}".format(
            code, ", ".join(_CATALOG.keys())))
    _LANGUAGE = code
    if _ORIGINAL is None:
        _ORIGINAL = SuggestionEngine.get_details

    original = _ORIGINAL

    def _wrapped(exc):
        return _translate(original(exc))

    SuggestionEngine.get_details = staticmethod(_wrapped)
    return _LANGUAGE


def reset_language() -> None:
    global _LANGUAGE, _ORIGINAL
    _LANGUAGE = "en"
    if _ORIGINAL is not None:
        SuggestionEngine.get_details = staticmethod(_ORIGINAL)
        _ORIGINAL = None
