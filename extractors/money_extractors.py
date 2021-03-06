# coding: utf-8
# TODO: повторить все для шила
# TODO: Подумать, как раскидать вилки по должностям, если их несколько.
#  Например, упорядочить уровни по возрастанию зп (сеньор больше миддла и т.п.)
#  Если такого нет, то можно раскидать к ближайшим (определяется по спану)
# TODO: воткнуть где-нибудь фразы "в месяц", "в год".
#  Можно будет выкидывать огромные "вилки", если не указано, что это в год
# TODO: еще надо учесть почасовку
# TODO: для нероссийских вакансий принимать доллары валютой по умолчанию
from __future__ import unicode_literals, division

import re

from yargy import (
    rule,
    and_, or_,
)
from yargy.interpretation import (
    fact,
    const,
    attribute
)
from yargy.predicates import (
    eq, length_eq,
    in_, in_caseless,
    gram, type,
    normalized, caseless, dictionary
)
from yargy.pipelines import caseless_pipeline

from natasha.extractors import Extractor

from natasha.dsl import (
    Normalizable,
    money as dsl
)

Money = fact(
    'Money',
    ['integer', 'fraction', 'multiplier', attribute('currency', 'RUB'), 'coins']
)


class Money(Money, Normalizable):
    @property
    def normalized(self):
        amount = self.integer
        if self.fraction:
            amount += self.fraction / 100
        if self.multiplier:
            amount *= self.multiplier
        if self.coins:
            amount += self.coins / 100
        return dsl.Money(amount, self.currency)


Rate = fact(
    'Rate',
    ['money', 'period']
)


class Rate(Rate, Normalizable):
    @property
    def normalized(self):
        return dsl.Rate(
            self.money.normalized,
            self.period
        )


Taxation = fact('Taxation', ['taxation'])

Range = fact(
    'Range',
    ['min', 'max', 'taxation']
)


class Range(Range, Normalizable):
    @property
    def normalized(self):
        # if self.max.multiplier and not self.min.multiplier:
        #     self.min.multiplier = self.max.multiplier
        min = self.min.normalized
        max = self.max.normalized
        # Приводим к одному масштабу (для вилок типа 150-250 т.р.)
        # TODO: иногда указывают миллионы (годовой доход в рублях), с ними не работает
        if (max.amount > 0) and (min.amount > 0):
            if max.amount / min.amount > 10:
                min.amount *= 1000
            elif min.amount / max.amount > 10:
                max.amount *= 1000
        if not min.currency:
            min.currency = max.currency
        # if (min.currency is not None) and (min.currency != 'RUB') and (max.currency is not None):
        #     max.currency
        elif min.currency != max.currency:
            min.currency = max.currency
        # для рублевых вилок типа 150-250 без указания тысяч домножаем на тысячу
        if (max.amount < 1000) and (min.amount < 1000) and (max.currency == 'RUB'):
            min.amount *= 1000
            max.amount *= 1000
        return dsl.Range(min, max)


DOT = eq('.')
INT = type('INT')

########
#
#   CURRENCY
#
##########


# EURO = or_(
#     normalized('евро'),
#     #in_(['€', 'EUR'])
#     eq('€'),
#     #eq('EUR')
# ).interpretation(
#     const(dsl.EURO)
# )
# EURO = caseless_pipeline(['евро', '€', 'eur'])#.interpretation(const(dsl.EURO))
EURO = or_(
    normalized('евро'),
    eq('€'),
    eq('EUR')
).interpretation(
    const(dsl.EURO)
)

DOLLARS = or_(
    normalized('доллар'),
    eq('$'),
    eq('USD')
).interpretation(
    const(dsl.DOLLARS)
)

RUBLES = or_(
    rule(normalized('рубль')),
    rule(
        or_(
            caseless('руб'),
            caseless('р'),
            eq('₽')
        ),
        DOT.optional()
    )
).interpretation(
    const(dsl.RUBLES)
)

CURRENCY = or_(
    EURO,
    DOLLARS,
    RUBLES
).interpretation(
    Money.currency
)
# TODO: копейки и центы тоже можно выпилить для ускорения
KOPEIKA = or_(
    rule(normalized('копейка')),
    rule(
        or_(
            caseless('коп'),
            caseless('к')
        ),
        DOT.optional()
    )
)

CENT = or_(
    normalized('цент'),
    eq('¢')
)

EUROCENT = normalized('евроцент')

COINS_CURRENCY = or_(
    KOPEIKA,
    rule(CENT),
    rule(EUROCENT)
)

############
#
#  MULTIPLIER
#
##########

# TODO: можно выпилить, чтобы шустрее работало
MILLIARD = or_(
    rule(caseless('млрд'), DOT.optional()),
    rule(normalized('миллиард'))
).interpretation(
    const(10 ** 9)
)

MILLION = or_(
    rule(caseless('млн'), DOT.optional()),
    rule(normalized('миллион')),
    rule(in_('мМmM'))
).interpretation(
    const(10 ** 6)
)

THOUSAND = or_(
    rule(caseless('т'), DOT),
    rule(caseless('к')),
    rule(caseless('k')),
    rule(caseless('тыс'), DOT.optional()),
    rule(normalized('тысяча'))
).interpretation(
    const(10 ** 3)
)

MULTIPLIER = or_(
    MILLIARD,
    MILLION,
    THOUSAND
).interpretation(
    Money.multiplier
)

########
#
#  NUMERAL
#
#######


NUMR = or_(
    gram('NUMR'),
    # https://github.com/OpenCorpora/opencorpora/issues/818
    dictionary({
        'ноль',
        'один'
    }),
)
# TODO: можно выпилить дробные части для снижения числа ложных срабатываний, их все равно не бывает в реальных вилках
#  Хотя одна вакаха в Tampere University of Technology реально была с дробями
MODIFIER = in_caseless({
    'целых',
    'сотых',
    'десятых'
})

PART = or_(
    rule(
        or_(
            INT,
            NUMR,
            MODIFIER
        )
    ),
    MILLIARD,
    MILLION,
    THOUSAND,
    CURRENCY,
    COINS_CURRENCY
)
# TODO: вот здесь можно поправить, чтобы телефоны не парсились
BOUND = in_('()//')

NUMERAL = rule(
    BOUND,
    PART.repeatable(),
    BOUND
)


#######
#
#   AMOUNT
#
########


def normalize_integer(value):
    integer = re.sub('[\s.,]+', '', value)
    return int(integer)


def normalize_fraction(value):
    fraction = value.ljust(2, '0')
    return int(fraction)


PART = and_(
    INT,
    length_eq(3)
)

SEP = in_(',.')

INTEGER = or_(
    rule(INT),
    rule(INT, PART),
    rule(INT, PART, PART),
    rule(INT, SEP, PART),
    rule(INT, SEP, PART, SEP, PART),
).interpretation(
    Money.integer.custom(normalize_integer)
)

FRACTION = and_(
    INT,
    or_(
        length_eq(1),
        length_eq(2)
    )
).interpretation(
    Money.fraction.custom(normalize_fraction)
)

AMOUNT = rule(
    INTEGER,
    rule(
        SEP,
        FRACTION
    ).optional(),
    MULTIPLIER.optional(),
    # NUMERAL.optional()
)

COINS_INTEGER = and_(
    INT,
    or_(
        length_eq(1),
        length_eq(2)
    )
).interpretation(
    Money.coins.custom(int)
)

COINS_AMOUNT = rule(
    COINS_INTEGER,
    NUMERAL.optional()
)

#########
#
#   MONEY
#
###########


MONEY = rule(
    AMOUNT,
    CURRENCY,
    # COINS_AMOUNT.optional(),
    # COINS_CURRENCY.optional()
).interpretation(
    Money
)

###########
#
#   RATE
#
##########


RATE_MONEY = MONEY.interpretation(
    Rate.money
)

PERIODS = {
    'день': dsl.DAY,
    'сутки': dsl.DAY,
    'час': dsl.HOUR,
    'смена': dsl.SHIFT
}

PERIOD = dictionary(
    PERIODS
).interpretation(
    Rate.period.normalized().custom(PERIODS.__getitem__)
)

PER = or_(
    eq('/'),
    in_caseless({'в', 'за'})
)

RATE = rule(
    RATE_MONEY,
    PER,
    PERIOD
).interpretation(
    Rate
)

#######
#
#   RANGE
#
########


DASH = eq('-')

RANGE_MONEY = rule(
    CURRENCY.optional(),
    AMOUNT,
    CURRENCY.optional()
).interpretation(
    Money
)

RANGE_MIN = rule(
    eq('от').optional(),
    RANGE_MONEY.interpretation(
        Range.min
    )
)

RANGE_MAX = rule(
    # eq('до').optional(),
    RANGE_MONEY.interpretation(
        Range.max
    )
)
# TODO: пока не интерпретируется
TAXATION = rule(caseless_pipeline(['чистыми', "грязными",
                                   "до налогов", "после налогов", "на руки",
                                   "gross", "гросс", 'net', "нетто",
                                   "до НДФЛ", "после НДФЛ",
                                   "до вычета НДФЛ", "после вычета НДФЛ"
                                   ]))
FORK = rule(dictionary({'fork', 'Вилка', 'ЗП', 'Оклад'}), eq(':').optional())
RANGE = rule(
    FORK.optional(),
    RANGE_MIN,
    or_(DASH, eq('до')),  # раньше был DASH.optional(),
    RANGE_MAX,
    TAXATION.interpretation(Range.taxation).optional()
).interpretation(
    Range
)


def parse_money_emojis(message: dict):
    big_money_emojis = {"moneyparrot",
                        "moneys",
                        "moneybag",
                        "money_with_wings",
                        "printing-money",
                        "money_mouth_face"}
    small_money_emojis = {'ramen',
                          'small'}
    widefork_emojis = {'widefork',
                       'rake2'}
    reactions = {(reaction['name'], reaction['count']) for reaction in message.get('reactions', [])}
    small_money_count = sum(count for name, count in reactions if name in small_money_emojis)
    big_money_count = sum(count for name, count in reactions if name in big_money_emojis)
    widefork_count = sum(count for name, count in reactions if name in widefork_emojis)
    return small_money_count, big_money_count, widefork_count


class MoneyRangeExtractor(Extractor):
    regex_digits_only = re.compile('^\d+\s?(-|–|до)\s?\d+$')
    regex_link = re.compile('<[^>]+>')
    currencies = {'$': 'USD',
                  '€': 'EUR'}

    def __init__(self):
        super(MoneyRangeExtractor, self).__init__(RANGE)

    def extract(self, text):
        """
        Фильтруем совпадения по условиям
        :param text:
        :return:
        """
        text = self.regex_link.sub('', text)
        matches = self(text).as_json
        res = []
        for match in matches:
            if 'fact' not in match:
                continue
            start, end = match['span'][0], match['span'][1]
            # Проверяем ложные срабатывания на неденежных интервалах
            if self.regex_digits_only.search(text[start:end]):
                continue
            if text[start] in self.currencies:
                match['fact']['min']['currency'] = self.currencies[text[start]]
                match['fact']['max']['currency'] = self.currencies[text[start]]
            res.append(match)
        return res
