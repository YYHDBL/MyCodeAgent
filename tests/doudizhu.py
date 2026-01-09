from enum import Enum
from typing import List, Optional, Set, Tuple, Dict
import random

class Suit(Enum):
    DIAMOND = '♦'
    CLUB = '♣'
    HEART = '♥'
    SPADE = '♠'

class Rank(Enum):
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14
    TWO = 15
    JOKER_SMALL = 16
    JOKER_BIG = 17

class Card:
    def __init__(self, rank: Rank, suit: Optional[Suit] = None):
        self.rank = rank
        self.suit = suit
    
    def __repr__(self):
        if self.rank == Rank.JOKER_SMALL:
            return '小王'
        if self.rank == Rank.JOKER_BIG:
            return '大王'
        return f'{self.suit.value}{self.rank.value}'
    
    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank
    
    def __lt__(self, other):
        return self.rank.value < other.rank.value
    
    def __hash__(self):
        return hash((self.rank, self.suit))

class Deck:
    def __init__(self):
        self.cards: List[Card] = []
        self._initialize()
    
    def _initialize(self):
        for suit in [Suit.DIAMOND, Suit.CLUB, Suit.HEART, Suit.SPADE]:
            for rank in Rank:
                if rank not in [Rank.JOKER_SMALL, Rank.JOKER_BIG]:
                    self.cards.append(Card(rank, suit))
        self.cards.append(Card(Rank.JOKER_SMALL))
        self.cards.append(Card(Rank.JOKER_BIG))
    
    def shuffle(self):
        random.shuffle(self.cards)
    
    def deal(self, count: int) -> List[Card]:
        dealt = self.cards[:count]
        self.cards = self.cards[count:]
        return dealt
    
    def __len__(self):
        return len(self.cards)

class Player:
    def __init__(self, name: str, is_ai: bool = False):
        self.name = name
        self.is_ai = is_ai
        self.hand: List[Card] = []
        self.is_landlord = False
    
    def add_cards(self, cards: List[Card]):
        self.hand.extend(cards)
        self.sort_hand()
    
    def sort_hand(self):
        self.hand.sort(key=lambda x: x.rank.value, reverse=True)
    
    def play_card(self, card: Card) -> bool:
        if card in self.hand:
            self.hand.remove(card)
            return True
        return False
    
    def play_cards(self, cards: List[Card]) -> bool:
        for card in cards:
            if card not in self.hand:
                return False
        for card in cards:
            self.hand.remove(card)
        return True
    
    def has_card(self, card: Card) -> bool:
        return card in self.hand
    
    def __repr__(self):
        return f'{self.name} ({"地主" if self.is_landlord else "农民"})'

class CardType(Enum):
    SINGLE = '单张'
    PAIR = '对子'
    TRIPLE = '三张'
    TRIPLE_WITH_ONE = '三带一'
    TRIPLE_WITH_PAIR = '三带一对'
    STRAIGHT = '顺子'
    PAIR_STRAIGHT = '连对'
    BOMB = '炸弹'
    ROCKET = '王炸'
    INVALID = '无效'

class HandAnalyzer:
    @staticmethod
    def get_rank_count(cards: List[Card]) -> Dict[Rank, int]:
        count = {}
        for card in cards:
            count[card.rank] = count.get(card.rank, 0) + 1
        return count
    
    @staticmethod
    def get_card_type(cards: List[Card]) -> Tuple[CardType, int]:
        if not cards:
            return CardType.INVALID, 0
        
        n = len(cards)
        rank_count = HandAnalyzer.get_rank_count(cards)
        counts = sorted(rank_count.values(), reverse=True)
        
        # 王炸
        if n == 2:
            ranks = list(rank_count.keys())
            if Rank.JOKER_SMALL in ranks and Rank.JOKER_BIG in ranks:
                return CardType.ROCKET, 17
        
        # 单张
        if n == 1:
            return CardType.SINGLE, cards[0].rank.value
        
        # 对子
        if n == 2 and counts[0] == 2:
            return CardType.PAIR, cards[0].rank.value
        
        # 三张
        if n == 3 and counts[0] == 3:
            return CardType.TRIPLE, cards[0].rank.value
        
        # 炸弹
        if n == 4 and counts[0] == 4:
            return CardType.BOMB, cards[0].rank.value
        
        # 三带一
        if n == 4 and counts == [3, 1]:
            main_rank = [r for r, c in rank_count.items() if c == 3][0]
            return CardType.TRIPLE_WITH_ONE, main_rank.value
        
        # 三带一对
        if n == 5 and counts == [3, 2]:
            main_rank = [r for r, c in rank_count.items() if c == 3][0]
            return CardType.TRIPLE_WITH_PAIR, main_rank.value
        
        # 顺子 (至少5张)
        if n >= 5:
            sorted_ranks = sorted([r.value for r in rank_count.keys()])
            if all(counts[i] == 1 for i in range(len(counts))):
                if max(sorted_ranks) - min(sorted_ranks) == n - 1:
                    if all(r <= Rank.ACE.value for r in sorted_ranks):
                        return CardType.STRAIGHT, max(sorted_ranks)
        
        # 连对 (至少3对)
        if n >= 6 and n % 2 == 0:
            if all(c == 2 for c in counts):
                sorted_ranks = sorted([r.value for r in rank_count.keys()])
                if max(sorted_ranks) - min(sorted_ranks) == len(sorted_ranks) - 1:
                    if all(r <= Rank.ACE.value for r in sorted_ranks):
                        return CardType.PAIR_STRAIGHT, max(sorted_ranks)
        
        return CardType.INVALID, 0
    
    @staticmethod
    def can_beat(cards: List[Card], last_cards: List[Card]) -> bool:
        card_type, value = HandAnalyzer.get_card_type(cards)
        last_type, last_value = HandAnalyzer.get_card_type(last_cards)
        
        if card_type == CardType.INVALID:
            return False
        
        # 王炸最大
        if card_type == CardType.ROCKET:
            return True
        
        # 炸弹可以打任何非炸弹和王炸
        if card_type == CardType.BOMB:
            if last_type not in [CardType.BOMB, CardType.ROCKET]:
                return True
            return value > last_value
        
        # 相同牌型比较
        if card_type == last_type:
            if card_type in [CardType.STRAIGHT, CardType.PAIR_STRAIGHT]:
                if len(cards) != len(last_cards):
                    return False
            return value > last_value
        
        return False

class DoudizhuGame:
    def __init__(self):
        self.players: List[Player] = []
        self.deck: Optional[Deck] = None
        self.landlord_cards: List[Card] = []
        self.current_player_index = 0
        self.last_played_cards: List[Card] = []
        self.last_player_index = -1
        self.pass_count = 0
    
    def init_game(self, player_names: List[str]):
        self.players = [Player(name, is_ai=(i != 0)) for i, name in enumerate(player_names)]
        self.deck = Deck()
        self.deck.shuffle()
        
        # 发牌 (每人17张，留3张底牌)
        for player in self.players:
            player.add_cards(self.deck.deal(17))
        self.landlord_cards = self.deck.deal(3)
    
    def set_landlord(self, player_index: int):
        self.players[player_index].is_landlord = True
        self.players[player_index].add_cards(self.landlord_cards)
        self.current_player_index = player_index
    
    def play_turn(self, player: Player, cards: List[Card]) -> bool:
        # 检查牌是否在手中
        for card in cards:
            if not player.has_card(card):
                return False
        
        # 如果是第一次出牌或新一轮
        if not self.last_played_cards or self.pass_count >= 2:
            card_type, _ = HandAnalyzer.get_card_type(cards)
            if card_type == CardType.INVALID:
                return False
        else:
            # 需要打过上家的牌
            if not HandAnalyzer.can_beat(cards, self.last_played_cards):
                return False
        
        # 出牌
        player.play_cards(cards)
        self.last_played_cards = cards.copy()
        self.pass_count = 0
        self.last_player_index = self.current_player_index
        
        return True
    
    def pass_turn(self, player: Player) -> bool:
        if not self.last_played_cards:
            return False  # 不能不出牌
        
        self.pass_count += 1
        return True
    
    def check_win(self, player: Player) -> bool:
        return len(player.hand) == 0
    
    def next_turn(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        
        # 如果连续两人不出，新的一轮
        if self.pass_count >= 2:
            self.last_played_cards = []
            self.pass_count = 0
            self.last_player_index = -1
    
    def get_current_player(self) -> Player:
        return self.players[self.current_player_index]
    
    def simple_ai_play(self, player: Player) -> List[Card]:
        if not self.last_played_cards:
            # 随便出一张最小的牌
            return [player.hand[-1]]
        
        card_type, value = HandAnalyzer.get_card_type(self.last_played_cards)
        
        # 尝试找能打过的牌
        if card_type == CardType.SINGLE:
            for card in reversed(player.hand):
                if card.rank.value > value:
                    return [card]
        elif card_type == CardType.PAIR:
            for i in range(len(player.hand) - 1):
                if player.hand[i].rank.value == player.hand[i + 1].rank.value:
                    if player.hand[i].rank.value > value:
                        return [player.hand[i], player.hand[i + 1]]
        
        # 找不到，尝试出炸弹
        rank_count = HandAnalyzer.get_rank_count(player.hand)
        for rank, count in rank_count.items():
            if count == 4 and rank.value > value:
                return [c for c in player.hand if c.rank == rank]
        
        # 出王炸
        jokers = [c for c in player.hand if c.rank in [Rank.JOKER_SMALL, Rank.JOKER_BIG]]
        if len(jokers) == 2:
            return jokers
        
        return []  # 不出
