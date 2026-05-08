import json
import os


CERTIFICATION_LABELS = {
    'industrial': '工丙',
    'digital-b': '數乙',
    'industrial-wiring-c': '工配丙',
    'computer-hardware-b': '硬裝乙',
    'computer-hardware-c': '硬裝丙',
}

UNMARKED_CERTIFICATION_LABEL = '未標記'

QUESTION_BANK_FILES = {
    'industrial': ['../src/data/questions-industrial.json', 'questions.json'],
    'digital-b': ['../src/data/questions-digital-b.json'],
    'industrial-wiring-c': ['../src/data/questions-industrial-wiring-c.json'],
    'computer-hardware-b': [
        '../src/data/questions-computer-hardware-b.json',
        '../src/data/questions-shared-info.json',
    ],
    'computer-hardware-c': [
        '../src/data/questions-computer-hardware-c.json',
        '../src/data/questions-shared-info.json',
    ],
}


def _safe_str(value):
    if value is None:
        return ''
    return str(value).strip()


def _parse_categories(value):
    if isinstance(value, list):
        return [_safe_str(item) for item in value if _safe_str(item)]
    if isinstance(value, tuple):
        return [_safe_str(item) for item in value if _safe_str(item)]
    if hasattr(value, 'tolist') and not isinstance(value, (str, bytes, dict)):
        list_value = value.tolist()
        if isinstance(list_value, list):
            return [_safe_str(item) for item in list_value if _safe_str(item)]
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [_safe_str(item) for item in parsed if _safe_str(item)]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return [_safe_str(part) for part in raw.split(',') if _safe_str(part)]
    return [_safe_str(value)] if _safe_str(value) else []


def get_valid_certification_ids():
    return tuple(CERTIFICATION_LABELS.keys())


def is_valid_certification_id(cert_id):
    return cert_id in CERTIFICATION_LABELS


def format_certification_label(cert_id):
    return CERTIFICATION_LABELS.get(cert_id, UNMARKED_CERTIFICATION_LABEL)


def get_certification_filter_options():
    return ['全部', *CERTIFICATION_LABELS.values(), UNMARKED_CERTIFICATION_LABEL]


def get_certification_filter_map():
    return {
        **{label: cert_id for cert_id, label in CERTIFICATION_LABELS.items()},
        UNMARKED_CERTIFICATION_LABEL: '',
    }


def extract_certification(row):
    cert = _safe_str(row.get('certification_id', ''))
    if is_valid_certification_id(cert):
        return cert

    settings = row.get('exam_settings')
    if settings:
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except Exception:
                settings = {}
        if isinstance(settings, dict):
            cert = _safe_str(settings.get('certificationId', ''))
            if is_valid_certification_id(cert):
                return cert

    categories = _parse_categories(row.get('categories', []))
    if any('工作項目10' in category for category in categories):
        return 'digital-b'

    return ''


def load_questions_by_certification():
    teacher_dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    question_banks = {}
    attempted_paths = {}

    for cert_id, relative_paths in QUESTION_BANK_FILES.items():
        combined_questions = []
        attempted_paths[cert_id] = []

        for relative_path in relative_paths:
            file_path = os.path.abspath(os.path.join(teacher_dashboard_dir, relative_path))
            attempted_paths[cert_id].append(file_path)
            if not os.path.exists(file_path):
                continue
            with open(file_path, 'r', encoding='utf-8') as file_obj:
                loaded = json.load(file_obj)
            if isinstance(loaded, list):
                combined_questions.extend(loaded)

        if combined_questions:
            question_banks[cert_id] = combined_questions

    return question_banks, attempted_paths