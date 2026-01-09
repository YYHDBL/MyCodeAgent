import pytest
from doudizhu import Card, Deck, Player, Rank, Suit, HandAnalyzer, CardType, DoudizhuGame

def test_card_creation():
    card = Card(Rank.ACE, Suit.SPADE)
    assert card.rank == Rank.ACE
    assert card.suit == Suit.SPADE
    assert str(card) == '♠14'

def test_joker_cards():
    small_joker = Card(Rank.JOKER_SMALL)
    big_joker = Card(Rank.JOKER_BIG)
    assert str(small_joker) == '小王'
    assert str(big_joker) == '大王'

def test_card_comparison():
    card1 = Card(Rank.FIVE, Suit.HEART)
    card2 = Card(Rank.TEN, Suit.CLUB)
    assert card1 < card2
    assert not (card1 == card2)

def test_deck_initialization():
    deck = Deck()
    assert len(deck.cards) == 54

def test_deck_deal():
    deck = Deck()
    cards = deck.deal(5)
    assert len(cards) == 5
    assert len(deck.cards) == 49

def test_player_add_cards():
    player = Player("测试玩家")
    cards = [Card(Rank.ACE, Suit.SPADE), Card(Rank.TEN, Suit.HEART)]
    player.add_cards(cards)
    assert len(player.hand) == 2

def test_player_play_card():
    player = Player("测试玩家")
    card = Card(Rank.ACE, Suit.SPADE)
    player.add_cards([card])
    assert player.play_card(card)
    assert len(player.hand) == 0

def test_single_card_type():
    card = Card(Rank.ACE, Suit.SPADE)
    card_type, value = HandAnalyzer.get_card_type([card])
    assert card_type == CardType.SINGLE
    assert value == Rank.ACE.value

def test_pair_type():
    cards = [Card(Rank.FIVE, Suit.HEART), Card(Rank.FIVE, Suit.CLUB)]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.PAIR
    assert value == Rank.FIVE.value

def test_triple_type():
    cards = [
        Card(Rank.SEVEN, Suit.HEART),
        Card(Rank.SEVEN, Suit.CLUB),
        Card(Rank.SEVEN, Suit.SPADE)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.TRIPLE
    assert value == Rank.SEVEN.value

def test_bomb_type():
    cards = [
        Card(Rank.EIGHT, Suit.HEART),
        Card(Rank.EIGHT, Suit.CLUB),
        Card(Rank.EIGHT, Suit.SPADE),
        Card(Rank.EIGHT, Suit.DIAMOND)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.BOMB
    assert value == Rank.EIGHT.value

def test_rocket_type():
    cards = [Card(Rank.JOKER_SMALL), Card(Rank.JOKER_BIG)]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.ROCKET
    assert value == 17

def test_triple_with_one():
    cards = [
        Card(Rank.NINE, Suit.HEART),
        Card(Rank.NINE, Suit.CLUB),
        Card(Rank.NINE, Suit.SPADE),
        Card(Rank.THREE, Suit.DIAMOND)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.TRIPLE_WITH_ONE
    assert value == Rank.NINE.value

def test_triple_with_pair():
    cards = [
        Card(Rank.TEN, Suit.HEART),
        Card(Rank.TEN, Suit.CLUB),
        Card(Rank.TEN, Suit.SPADE),
        Card(Rank.FOUR, Suit.DIAMOND),
        Card(Rank.FOUR, Suit.HEART)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.TRIPLE_WITH_PAIR
    assert value == Rank.TEN.value

def test_straight_type():
    cards = [
        Card(Rank.FIVE, Suit.HEART),
        Card(Rank.SIX, Suit.CLUB),
        Card(Rank.SEVEN, Suit.SPADE),
        Card(Rank.EIGHT, Suit.DIAMOND),
        Card(Rank.NINE, Suit.HEART)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.STRAIGHT
    assert value == Rank.NINE.value

def test_pair_straight_type():
    cards = [
        Card(Rank.FIVE, Suit.HEART), Card(Rank.FIVE, Suit.CLUB),
        Card(Rank.SIX, Suit.SPADE), Card(Rank.SIX, Suit.DIAMOND),
        Card(Rank.SEVEN, Suit.HEART), Card(Rank.SEVEN, Suit.CLUB)
    ]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.PAIR_STRAIGHT
    assert value == Rank.SEVEN.value

def test_invalid_type():
    cards = [Card(Rank.FIVE, Suit.HEART), Card(Rank.TEN, Suit.CLUB)]
    card_type, value = HandAnalyzer.get_card_type(cards)
    assert card_type == CardType.INVALID
    assert value == 0

def test_can_beat_single():
    card1 = [Card(Rank.ACE, Suit.SPADE)]
    card2 = [Card(Rank.TWO, Suit.HEART)]
    assert HandAnalyzer.can_beat(card2, card1)
    assert not HandAnalyzer.can_beat(card1, card2)

def test_can_beat_pair():
    pair1 = [Card(Rank.FIVE, Suit.HEART), Card(Rank.FIVE, Suit.CLUB)]
    pair2 = [Card(Rank.SIX, Suit.SPADE), Card(Rank.SIX, Suit.DIAMOND)]
    assert HandAnalyzer.can_beat(pair2, pair1)

def test_bomb_beats_single():
    single = [Card(Rank.ACE, Suit.SPADE)]
    bomb = [
        Card(Rank.FIVE, Suit.HEART),
        Card(Rank.FIVE, Suit.CLUB),
        Card(Rank.FIVE, Suit.SPADE),
        Card(Rank.FIVE, Suit.DIAMOND)
    ]
    assert HandAnalyzer.can_beat(bomb, single)

def test_rocket_beats_bomb():
    bomb = [
        Card(Rank.FIVE, Suit.HEART),
        Card(Rank.FIVE, Suit.CLUB),
        Card(Rank.FIVE, Suit.SPADE),
        Card(Rank.FIVE, Suit.DIAMOND)
    ]
    rocket = [Card(Rank.JOKER_SMALL), Card(Rank.JOKER_BIG)]
    assert HandAnalyzer.can_beat(rocket, bomb)

def test_game_initialization():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    assert len(game.players) == 3
    assert len(game.landlord_cards) == 3
    for player in game.players:
        assert len(player.hand) == 17

def test_set_landlord():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    game.set_landlord(0)
    assert game.players[0].is_landlord
    assert len(game.players[0].hand) == 20  # 17 + 3

def test_play_turn():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    game.set_landlord(0)
    player = game.get_current_player()
    cards = [player.hand[-1]]
    assert game.play_turn(player, cards)
    assert game.last_played_cards == cards

def test_pass_turn():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    game.set_landlord(0)
    player = game.get_current_player()
    cards = [player.hand[-1]]
    game.play_turn(player, cards)
    game.next_turn()
    
    next_player = game.get_current_player()
    assert game.pass_turn(next_player)
    assert game.pass_count == 1

def test_check_win():
    game = DoudizhuGame()
    player = Player("测试玩家")
    assert not game.check_win(player)
    player.hand.clear()
    assert game.check_win(player)

def test_next_turn():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    assert game.current_player_index == 0
    game.next_turn()
    assert game.current_player_index == 1
    game.next_turn()
    assert game.current_player_index == 2
    game.next_turn()
    assert game.current_player_index == 0

def test_simple_ai_play():
    game = DoudizhuGame()
    game.init_game(["玩家1", "玩家2", "玩家3"])
    game.set_landlord(1)
    
    ai_player = game.players[1]
    cards_to_play = game.simple_ai_play(ai_player)
    assert len(cards_to_play) > 0
    
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
