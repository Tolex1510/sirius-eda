"""Reject generation loops and produce a factual response from retrieved evidence."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re


def repetitive(text: str) -> bool:
    words=re.findall(r'\w+',text.lower())
    if len(words)<20:
        return False
    for size in (3,4,6,8):
        grams=Counter(tuple(words[i:i+size]) for i in range(len(words)-size+1))
        count=max(grams.values(),default=0)
        if count>=4 and count*size>=len(words)*0.30:
            return True
    return len(words)>=60 and len(set(words))/len(words)<0.22


def rubles(value) -> str:
    try:
        text=f'{Decimal(str(value)):.2f}'.replace('.',',')
        return text.removesuffix(',00')+' ₽'
    except InvalidOperation:
        return str(value)+' ₽'


def evidence_answer(sources) -> str:
    dishes=[]
    for source in sources:
        match=re.search(r'Блюдо: (.+?)\. Цена: ([\d.]+) RUB',source.text)
        if match:
            dishes.append(f'• {match.group(1)} — {rubles(match.group(2))}')
    if dishes:
        return 'Вот подходящие блюда из меню:\n'+'\n'.join(dishes[:3])+'\nПодробности — в источниках ниже.'
    if sources:
        return 'Вот что указано в справке:\n\n'+'\n\n'.join(s.text[:600] for s in sources[:2])
    return 'Не получилось составить надёжный ответ. Попробуйте уточнить вопрос или откройте меню.'
