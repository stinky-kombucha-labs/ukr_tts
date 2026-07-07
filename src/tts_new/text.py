from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import unicodedata

from .config import TextConfig


QUOTE_CHARS = set('"“”„«»')
PLAIN_QUOTE_CHARS = set('"“”„')

NOISE_PATTERNS = [
    re.compile(r"^\s*(?:\*+\s*)?(?:TL|T/L|Translator)\s+note\s*[:：]", re.IGNORECASE),
    re.compile(r"^\s*\*.+"),
    re.compile(r"^\s*(?:※|×|\*|＊|=|_|#|~){3,}\s*$"),
    re.compile(r"^\s*[—–\-─]{2,}\s*$"),
    re.compile(r"^\s*(?:…|\.{3,})+\s*$"),
    re.compile(r"^\s*```"),
]

SERVICE_OUTPUT_PATTERNS = [
    re.compile(r"^\s*перекладач\s+англійської\s+на\s+українську\b", re.IGNORECASE),
    re.compile(r"\bлише\s+переклад\b", re.IGNORECASE),
    re.compile(r"\bтільки\s+переклад\b", re.IGNORECASE),
    re.compile(r"\bбез\s+пояснень\b", re.IGNORECASE),
    re.compile(r"^\s*(переклад|українською|відповідь)\s*:\s*$", re.IGNORECASE),
    re.compile(r"^\s*ось\s+переклад\b", re.IGNORECASE),
]

REVERSED_GUILLEMET_PAIR_RE = re.compile(
    r"»[ \t]*([A-Za-zА-Яа-яІіЇїЄєҐґ0-9]"
    r"[^«»\n.!?;:—–]{0,100}?"
    r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9])[ \t]*«"
)

SPACE_RE = re.compile(r"\s+")
LEGACY_DELIMITER_RE = re.compile(r'([.!?,:;…][\s"\'“”«»]*)')

# Prepared text must contain only Ukrainian letters, digits and punctuation:
# the engine lowercases everything and transliterates Latin letter-by-letter
# ("XIV" -> "ксів", "X" -> "кс"), so every Latin token is converted here,
# where the result stays visible in prepared/*.txt.
VALID_ROMAN_RE = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Latin runs not glued to Cyrillic (those stay for the mixed_script report).
LATIN_RUN_RE = re.compile(r"(?<![А-Яа-яІіЇїЄєҐґ])[A-Za-z]+(?![А-Яа-яІіЇїЄєҐґ])")

# After these words (in any grammatical case) a single I/V/X/… is a Roman
# numeral, not a letter name: "том I" -> "том 1", but "Містер X" -> "Ікс".
SECTION_WORD_RE = re.compile(
    r"^(розділ|том|частин|книг|глав|акт|сцен|пункт|параграф|епізод|сезон|арк)"
    r"(а|ах|и|і|ів|ом|ому|ої|ою|у|е)?$",
    re.IGNORECASE,
)

# Ukrainian names of Latin letters ("Містер X" -> "Містер Ікс").
LETTER_NAMES = {
    "a": "а", "b": "бе", "c": "це", "d": "де", "e": "е", "f": "еф",
    "g": "же", "h": "аш", "i": "і", "j": "йот", "k": "ка", "l": "ель",
    "m": "ем", "n": "ен", "o": "о", "p": "пе", "q": "ку", "r": "ер",
    "s": "ес", "t": "те", "u": "у", "v": "ве", "w": "дубль-ве",
    "x": "ікс", "y": "ігрек", "z": "зет",
}

# Digraph-first transliteration for ordinary Latin words (ported from the
# engine's formatter so the result is visible at the prepare stage).
TRANSLITERATION = {
    "qu": "кв", "ch": "ч", "sh": "ш", "ph": "ф", "kh": "х", "yo": "йо",
    "yu": "ю", "ya": "я", "ye": "є", "yi": "ї", "zh": "ж", "ts": "ц",
    "th": "т", "a": "а", "b": "б", "c": "ц", "d": "д", "e": "е", "f": "ф",
    "g": "ґ", "h": "г", "i": "і", "j": "дж", "k": "к", "l": "л", "m": "м",
    "n": "н", "o": "о", "p": "п", "q": "кв", "r": "р", "s": "с", "t": "т",
    "u": "ю", "v": "в", "w": "в", "x": "кс", "y": "і", "z": "з",
}

# Pronunciations for well-known abbreviations (semantic translations proven in
# the old tts project; initialisms are spelled with letter names because the
# model cannot pronounce consonant clusters like "ХП").
ABBREVIATIONS = {
    "MMORPG": "ем-ем-о ер-пе-ге", "ASAP": "якнайшвидше", "WIFI": "вайфай",
    "PVP": "гравець проти гравця", "PVE": "гравець проти середовища",
    "NPC": "ен-пе-ес", "VIP": "віп", "XP": "досвід", "HP": "ха-пе",
    "MP": "ем-пе", "SP": "ес-пе", "AP": "а-пе", "DP": "де-пе", "EP": "е-пе",
    "ATK": "атака", "DEF": "захист", "STR": "сила", "AGI": "спритність",
    "INT": "інтелект", "VIT": "витривалість", "LUK": "удача",
    "DEX": "спритність", "CEO": "директор", "AI": "штучний інтелект",
    "UI": "інтерфейс", "ID": "ідентифікатор", "OK": "окей", "VS": "проти",
    "GM": "геймстер", "OP": "надпотужний", "AFK": "відійшов",
    "DPS": "урон за секунду", "AOE": "урон по площі", "DOT": "урон з часом",
    "RPG": "ер-пе-ге", "FPS": "еф-пе-ес", "RNG": "випадковість",
    "EXP": "досвід", "LVL": "рівень", "MAX": "максимум",
    "SSS": "ес-ес-ес", "SSR": "ес-ес-ер", "SS": "ес-ес", "SR": "ес-ер",
    "UR": "у-ер", "LR": "ел-ер", "MR": "ем-ер", "HR": "ха-ер",
    "USA": "ес-ше-а", "UK": "Велика Британія", "EU": "євросоюз",
    "USD": "долари", "VR": "віртуальна реальність",
    "AR": "доповнена реальність", "GPS": "джі-пі-ес", "TV": "телевізор",
    "PC": "комп'ютер", "DVD": "ді-ві-ді", "CD": "компакт-диск",
    "USB": "ю-ес-бі", "SMS": "ес-ем-ес", "SOS": "сос", "FBI": "еф-бе-ер",
    "CIA": "це-ер-у", "PHD": "доктор наук", "IQ": "ай-кью",
    "EQ": "емоційний інтелект", "DNA": "де-ен-ка", "RNA": "ер-ен-ка",
    "UFO": "ен-ел-о", "FAQ": "часті питання", "BFF": "найкращий друг",
    "OMG": "о боже", "WTF": "що за", "LOL": "смішно", "BTW": "до речі",
    "FYI": "до відома", "QR": "кю-ар",
}

# Translators often type Roman numerals with Cyrillic lookalikes ("ХХ
# століття"). Recognize them only in unambiguous contexts (century noun after,
# section word before); a lone "І" stays — it is usually the conjunction.
CYRILLIC_TO_ROMAN = str.maketrans("ІВХЛСДМ", "IVXLCDM")
CYRILLIC_ROMAN_TOKEN_RE = re.compile(
    r"(?<![А-Яа-яІіЇїЄєҐґ'-])([ІВХЛСДМ]{1,6})(?![А-Яа-яІіЇїЄєҐґ'-])"
)

# Cyrillic ALL-CAPS: known initialisms get explicit pronunciations; runs with
# no vowel cannot be shouted words, so they are spelled with letter names
# ("ХП" -> "ха-пе"). Vowel-containing caps ("УВАГА!", "СТОП") stay untouched.
CYRILLIC_ABBREVIATIONS = {
    "ЦРУ": "це-ер-у", "НЛО": "ен-ел-о", "США": "ес-ше-а", "ООН": "о-о-ен",
    "СБУ": "ес-бе-у", "ЄС": "євросоюз", "МВС": "ем-ве-ес", "НАТО": "нато",
}
CYRILLIC_CAPS_RUN_RE = re.compile(
    r"(?<![А-Яа-яІіЇїЄєҐґ'-])([А-ЯІЇЄҐ]{2,})(?![А-Яа-яІіЇїЄєҐґ'-])"
)
CYRILLIC_VOWELS = set("аеєиіїоуюя")
CYRILLIC_LETTER_NAMES = {
    "б": "бе", "в": "ве", "г": "ге", "ґ": "ґе", "д": "де", "ж": "же",
    "з": "зе", "й": "йот", "к": "ка", "л": "ел", "м": "ем", "н": "ен",
    "п": "пе", "р": "ер", "с": "ес", "т": "те", "ф": "еф", "х": "ха",
    "ц": "це", "ч": "че", "ш": "ша", "щ": "ща",
}

# "у XVII столітті" must become an ordinal in the right case ("сімнадцятому"),
# not a cardinal ("сімнадцять"). Roman numerals before a century noun are
# always ordinals; Arabic digits are converted only for unambiguous case forms
# ("столітті", "століттям") so that counts ("минуло три століття") stay intact.
CENTURY_NOUN_RE = re.compile(
    r"\s+(столітт(?:ями|ях|ям|і|я)|сторічч(?:ями|ях|ям|і|я)|століть|сторіч)\b"
)
DIGIT_CENTURY_RE = re.compile(r"\b(\d{1,2})(\s+)(столітті|сторіччі|століттям|сторіччям)\b")
GENITIVE_HINTS = {
    "до", "від", "після", "близько", "наприкінці", "протягом", "упродовж",
    "з", "із", "зі", "початку", "кінця", "середини", "половини", "межі", "зламу",
}
ORDINAL_ENDINGS = {
    # noun form -> (hard-stem ending, soft-stem ending) for the ordinal
    "столітті": ("ому", "ьому"), "сторіччі": ("ому", "ьому"),
    "століттям": ("им", "ім"), "сторіччям": ("им", "ім"),
    "століттями": ("ими", "іми"), "сторіччями": ("ими", "іми"),
    "століттях": ("их", "іх"), "сторіччях": ("их", "іх"),
    "століть": ("их", "іх"), "сторіч": ("их", "іх"),
    "століття": ("е", "є"), "сторіччя": ("е", "є"),
}
ORDINAL_GENITIVE = ("ого", "ього")


@dataclass(frozen=True)
class PreparedText:
    text: str
    lines: list[str]
    dropped_lines: int
    max_line_chars: int
    glossary_replacements: int = 0


def load_glossary(path: Path) -> list[tuple[re.Pattern, str]]:
    """User-editable word replacements from glossary.json.

    Key "слово" replaces the exact word; key "основ*" replaces the word stem
    and keeps the grammatical ending ("російськ*": "русняв" turns
    "російського" into "руснявого"). Exact entries run before stem entries;
    the original capitalization is preserved.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    exact = {k: v for k, v in data.items() if not k.endswith("*")}
    prefix = {k[:-1]: v for k, v in data.items() if k.endswith("*")}

    rules: list[tuple[re.Pattern, str]] = []
    for key, value in sorted(exact.items(), key=lambda kv: -len(kv[0])):
        rules.append((re.compile(rf"\b{re.escape(key)}\b", re.IGNORECASE), value))
    for key, value in sorted(prefix.items(), key=lambda kv: -len(kv[0])):
        rules.append(
            (re.compile(rf"\b{re.escape(key)}(?=[А-Яа-яІіЇїЄєҐґ])", re.IGNORECASE), value)
        )
    return rules


def apply_glossary(text: str, rules: list[tuple[re.Pattern, str]]) -> tuple[str, int]:
    total = 0
    for pattern, value in rules:
        def repl(match: re.Match, value: str = value) -> str:
            token = match.group(0)
            if token.isupper() and len(token) > 1:
                return value.upper()
            if token[0].isupper():
                return value[0].upper() + value[1:]
            return value

        text, count = pattern.subn(repl, text)
        total += count
    return text, total


def is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return any(pattern.search(s) for pattern in NOISE_PATTERNS)


def is_service_output(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if "=>" in s or "→" in s:
        return True
    return any(pattern.search(s) for pattern in SERVICE_OUTPUT_PATTERNS)


def roman_to_arabic(roman: str) -> int:
    result = 0
    prev = 0
    for char in reversed(roman):
        value = ROMAN_VALUES[char]
        result += value if value >= prev else -value
        prev = value
    return result


def _ordinal_uk(number: int, noun: str, genitive: bool) -> str:
    """Ukrainian ordinal for a century noun: 17 + "столітті" -> "сімнадцятому"."""
    from num2words import num2words

    words = num2words(number, lang="uk", to="ordinal").split()
    last = words[-1]
    soft = last.endswith("ій")  # "третій" declines with soft endings
    stem = last[:-2]
    if genitive:
        ending = ORDINAL_GENITIVE[1] if soft else ORDINAL_GENITIVE[0]
    else:
        hard, soft_ending = ORDINAL_ENDINGS[noun]
        ending = soft_ending if soft else hard
    words[-1] = stem + ending
    return " ".join(words)


def _century_ordinal(number: int, noun: str, before: str) -> str:
    genitive = False
    if noun in ("століття", "сторіччя"):
        prev = re.search(r"([А-Яа-яІіЇїЄєҐґ']+)\s*$", before)
        genitive = bool(prev) and prev.group(1).lower() in GENITIVE_HINTS
    return _ordinal_uk(number, noun, genitive)


def convert_digit_centuries(line: str) -> str:
    def convert(match: re.Match) -> str:
        number = int(match.group(1))
        noun = match.group(3)
        return _century_ordinal(number, noun, match.string[: match.start()]) + match.group(2) + noun

    return DIGIT_CENTURY_RE.sub(convert, line)


def normalize_symbols(line: str) -> str:
    line = re.sub(r"\s*°\s*[CС]\b", " градусів за Цельсієм", line)
    line = re.sub(r"\s*°\s*F\b", " градусів за Фаренгейтом", line)
    line = line.replace("°", " градусів ")
    line = re.sub(r"\s*%", " відсотків", line)
    line = re.sub(r"№\s*", "номер ", line)
    line = line.replace("&", " і ")
    line = re.sub(r"§\s*", "параграф ", line)
    line = line.replace("=", " дорівнює ")
    # "+" is the engine's internal stress marker — never let it through.
    line = line.replace("+", " плюс ")
    return line


def _transliterate_word(word: str) -> str:
    capitalize = word[0].isupper()
    word = word.lower()
    out = []
    i = 0
    while i < len(word):
        if word[i : i + 2] in TRANSLITERATION:
            out.append(TRANSLITERATION[word[i : i + 2]])
            i += 2
        else:
            out.append(TRANSLITERATION[word[i]])
            i += 1
    result = "".join(out)
    return result.capitalize() if capitalize else result


def convert_latin_tokens(line: str) -> str:
    def convert(match: re.Match) -> str:
        token = match.group(0)
        upper = token.upper()
        before = match.string[: match.start()]
        century = CENTURY_NOUN_RE.match(match.string[match.end():])

        if upper in ABBREVIATIONS:
            return ABBREVIATIONS[upper]
        if len(token) >= 2 and token.isupper() and VALID_ROMAN_RE.match(token):
            number = roman_to_arabic(token)
            if century:
                return _century_ordinal(number, century.group(1), before)
            return str(number)
        if len(token) == 1:
            if upper in ROMAN_VALUES:
                if century:
                    return _century_ordinal(ROMAN_VALUES[upper], century.group(1), before)
                word = re.search(r"([А-Яа-яІіЇїЄєҐґ]+)\s*$", before)
                if word and SECTION_WORD_RE.match(word.group(1)):
                    return str(ROMAN_VALUES[upper])
            name = LETTER_NAMES[token.lower()]
            return name.capitalize() if token.isupper() else name
        if token.isupper():
            return "-".join(LETTER_NAMES[ch] for ch in token.lower())
        return _transliterate_word(token)

    return LATIN_RUN_RE.sub(convert, line)


def convert_cyrillic_romans(line: str) -> str:
    def convert(match: re.Match) -> str:
        token = match.group(1)
        roman = token.translate(CYRILLIC_TO_ROMAN)
        if not VALID_ROMAN_RE.match(roman):
            return token
        number = roman_to_arabic(roman)
        before = match.string[: match.start()]
        century = CENTURY_NOUN_RE.match(match.string[match.end():])
        if century and token != "І":
            return _century_ordinal(number, century.group(1), before)
        word = re.search(r"([А-Яа-яІіЇїЄєҐґ]+)\s*$", before)
        if word and SECTION_WORD_RE.match(word.group(1)):
            return str(number)
        return token

    return CYRILLIC_ROMAN_TOKEN_RE.sub(convert, line)


def convert_cyrillic_acronyms(line: str) -> str:
    def convert(match: re.Match) -> str:
        token = match.group(1)
        if token in CYRILLIC_ABBREVIATIONS:
            return CYRILLIC_ABBREVIATIONS[token]
        if not CYRILLIC_VOWELS.intersection(token.lower()):
            return "-".join(CYRILLIC_LETTER_NAMES[ch] for ch in token.lower())
        return token

    return CYRILLIC_CAPS_RUN_RE.sub(convert, line)


def normalize_guillemets(line: str) -> str:
    if not any(ch in line for ch in QUOTE_CHARS):
        return line

    out: list[str] = []
    opening = True
    for ch in line:
        if ch in PLAIN_QUOTE_CHARS:
            out.append("«" if opening else "»")
            opening = not opening
        else:
            out.append(ch)
    line = "".join(out)

    for _ in range(4):
        line, changed = REVERSED_GUILLEMET_PAIR_RE.subn(r"«\1»", line)
        if not changed:
            break
    line = re.sub(r"^([ \t]*)»[ \t]*", r"\1«", line)
    line = re.sub(r"[ \t]*«([.!?…;:,.]*)$", r"»\1", line)
    return line


def normalize_quote_spacing(line: str) -> str:
    if "«" not in line and "»" not in line:
        return line
    line = re.sub(r"([:;,])[ \t]*»[ \t]*", r"\1 «", line)
    line = re.sub(r"«[ \t]+", "«", line)
    line = re.sub(r"[ \t]+»", "»", line)
    line = re.sub(r"(?<=[\w\]\)».,!?;:—–])[ \t]*«", r" «", line)
    line = re.sub(r"»(?=[\w\[\(«])", r"» ", line)
    line = re.sub(r"»[ \t]*[—–][ \t]*", r"» — ", line)
    line = re.sub(r"»[ \t]+([.,!?;:])", r"»\1", line)
    return line


def clean_line(line: str) -> str:
    line = line.replace("№", "номер ")  # NFKC would turn № into Latin "No"
    line = unicodedata.normalize("NFKC", line)
    line = line.replace("\ufeff", "").replace("\u200b", "").replace("\u2060", "")
    line = line.strip()
    if not line:
        return ""

    if is_noise_line(line) or is_service_output(line):
        return ""

    replacements = {
        "`": "'",
        "ʼ": "'",
        "’": "'",
        "‘": "'",
        "※": " ",
        "＊": " ",
        "*": " ",
        "#": " ",
        "~": " ",
        "—": " — ",
        "–": " — ",
        "―": " — ",
        "[": "(",
        "]": ")",
    }
    for old, new in replacements.items():
        line = line.replace(old, new)

    line = normalize_symbols(line)
    line = convert_latin_tokens(line)
    line = convert_digit_centuries(line)
    line = convert_cyrillic_romans(line)
    line = convert_cyrillic_acronyms(line)
    line = normalize_guillemets(line)
    line = re.sub(r"\.{3,}", "…", line)
    line = re.sub(r"…{2,}", "…", line)
    line = re.sub(r"\s*[—–\-─]{2,}\s*", " — ", line)
    line = re.sub(r"[ \t]+([.,!?;:])", r"\1", line)
    line = normalize_quote_spacing(line)
    line = SPACE_RE.sub(" ", line).strip()
    return line


def split_segments(text: str, config: TextConfig) -> list[str]:
    """Segmentation ported from the proven tts/scripts/normalize_lines.py.

    Joins the whole chapter, splits by punctuation while keeping delimiters,
    then packs sentence fragments into one physical line until adding the next
    fragment would exceed target_chars.
    """
    content = " ".join(text.split())
    content = re.sub(r"«\s+", "«", content)
    content = re.sub(r"\s+»", "»", content)
    content = re.sub(r"([»)\]])\s+([.,!?;:])", r"\1\2", content)
    content = re.sub(r"\s+([.,!?;:])", r"\1", content)
    if not content:
        return []

    parts = LEGACY_DELIMITER_RE.split(content)
    sentences: list[str] = []
    i = 0
    while i < len(parts):
        sentence = parts[i]
        if i + 1 < len(parts):
            sentence += parts[i + 1]
            i += 2
        else:
            i += 1
        sentence = sentence.strip()
        if sentence and not re.fullmatch(r"[.,!?;:…]+", sentence):
            sentences.append(sentence)

    lines: list[str] = []
    current_line = ""
    for sentence in sentences:
        if not current_line:
            current_line = sentence
        elif len(current_line) + len(sentence) + 1 <= config.target_chars:
            current_line += " " + sentence
        else:
            lines.append(current_line)
            current_line = sentence

    if current_line:
        lines.append(current_line)
    return lines


def prepare_text(
    text: str,
    config: TextConfig,
    glossary: list[tuple[re.Pattern, str]] | None = None,
) -> PreparedText:
    replaced = 0
    if glossary:
        text, replaced = apply_glossary(text, glossary)

    cleaned_lines: list[str] = []
    dropped = 0
    for raw_line in text.splitlines():
        cleaned = clean_line(raw_line)
        if cleaned:
            cleaned_lines.append(cleaned)
        elif raw_line.strip():
            dropped += 1

    joined = " ".join(cleaned_lines)
    segments = split_segments(joined, config)
    prepared = "\n".join(segments)
    if prepared:
        prepared += "\n"
    return PreparedText(
        text=prepared,
        lines=segments,
        dropped_lines=dropped,
        max_line_chars=max((len(line) for line in segments), default=0),
        glossary_replacements=replaced,
    )
