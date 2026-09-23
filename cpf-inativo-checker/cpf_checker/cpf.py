"""Normalização e validação local de CPF (dígitos verificadores).

Validar localmente antes de consultar a Receita evita gastar consultas pagas
com CPFs que nem existem (digitação errada, campo com lixo etc.).
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")


def normalize(value: object) -> str:
    """Remove pontuação e completa com zeros à esquerda (11 dígitos).

    Planilhas costumam transformar CPF em número e perder os zeros iniciais
    (ex.: 01234567890 vira 1234567890), por isso completamos com zfill.
    Retorna string vazia quando não há dígitos.
    """
    if value is None:
        return ""
    text = str(value).strip()
    # "12345678901.0" vindo de planilha lida como float
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return ""
    return digits.zfill(11) if len(digits) <= 11 else digits


def _check_digit(digits: str) -> int:
    weight = len(digits) + 1
    total = sum(int(d) * (weight - i) for i, d in enumerate(digits))
    rest = total % 11
    return 0 if rest < 2 else 11 - rest


def is_valid(cpf: str) -> bool:
    """True se o CPF (já normalizado) tem 11 dígitos e verificadores corretos."""
    if len(cpf) != 11 or not cpf.isdigit():
        return False
    if cpf == cpf[0] * 11:  # 000.000.000-00, 111.111.111-11 ...
        return False
    first = _check_digit(cpf[:9])
    second = _check_digit(cpf[:9] + str(first))
    return cpf[9:] == f"{first}{second}"


def mask(cpf: str) -> str:
    """Mascara o CPF para logs (LGPD): 123.***.***-01."""
    if len(cpf) != 11:
        return "***"
    return f"{cpf[:3]}.***.***-{cpf[9:]}"


def format_cpf(cpf: str) -> str:
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
