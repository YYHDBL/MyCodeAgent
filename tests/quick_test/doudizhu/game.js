// 斗地主游戏逻辑 - 4人版

// 游戏状态
let gameState = {
    deck: [],
    players: [[], [], [], []], // 0: 我, 1: 电脑1, 2: 电脑2, 3: 电脑3
    bottomCards: [],
    landlord: -1,
    currentPlayer: 0,
    lastPlayedCards: [],
    lastPlayer: -1
};

// 初始化牌组
function initDeck() {
    const suits = ['\u2660', '\u2665', '\u2663', '\u2666'];
    const values = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2'];
    const deck = [];
    
    for (let suit of suits) {
        for (let i = 0; i < values.length; i++) {
            deck.push({ suit, value: values[i], rank: i });
        }
    }
    
    deck.push({ suit: '', value: '小王', rank: 13 });
    deck.push({ suit: '', value: '大王', rank: 14 });
    
    return shuffle(deck);
}

function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

function dealCards() {
    gameState.deck = initDeck();
    gameState.bottomCards = gameState.deck.slice(0, 2);
    gameState.players[0] = gameState.deck.slice(2, 15);
    gameState.players[1] = gameState.deck.slice(15, 28);
    gameState.players[2] = gameState.deck.slice(28, 41);
    gameState.players[3] = gameState.deck.slice(41, 54);
    
    for (let i = 0; i < 4; i++) {
        sortCards(gameState.players[i]);
    }
}

function sortCards(cards) {
    cards.sort((a, b) => b.rank - a.rank);
}

function startGame() {
    dealCards();
    updateUI();
    
    document.getElementById('btnStart').style.display = 'none';
    document.getElementById('gameStatus').textContent = '请选择是否叫地主';
    document.getElementById('btnCall').style.display = 'inline-block';
    document.getElementById('btnPassCall').style.display = 'inline-block';
}

function callLandlord() {
    gameState.landlord = 0;
    gameState.players[0].push(...gameState.bottomCards);
    sortCards(gameState.players[0]);
    
    document.getElementById('myRole').textContent = '地主';
    document.getElementById('btnCall').style.display = 'none';
    document.getElementById('btnPassCall').style.display = 'none';
    
    startPlaying();
}

function passCall() {
    gameState.landlord = Math.floor(Math.random() * 3) + 1;
    gameState.players[gameState.landlord].push(...gameState.bottomCards);
    sortCards(gameState.players[gameState.landlord]);
    
    const roles = ['', '电脑1', '电脑2', '电脑3'];
    const selectors = ['.left-player .role', '.top-player .role', '.right-player .role'];
    document.querySelector(selectors[gameState.landlord - 1]).textContent = '地主';
    
    document.getElementById('btnCall').style.display = 'none';
    document.getElementById('btnPassCall').style.display = 'none';
    
    startPlaying();
}

function startPlaying() {
    document.getElementById('gameStatus').textContent = '游戏开始，地主先出牌';
    updateUI();
    
    gameState.currentPlayer = gameState.landlord;
    
    if (gameState.currentPlayer === 0) {
        showPlayButtons();
    } else {
        computerPlay();
    }
}

function showPlayButtons() {
    document.getElementById('btnPlay').style.display = 'inline-block';
    document.getElementById('btnPass').style.display = 'inline-block';
    document.getElementById('btnHint').style.display = 'inline-block';
}

function playCards() {
    const selected = getSelectedCards();
    if (selected.length === 0) {
        alert('请选择要出的牌');
        return;
    }
    
    if (gameState.lastPlayer !== 0 && gameState.lastPlayedCards.length > 0) {
        if (!isValidPlay(selected, gameState.lastPlayedCards)) {
            alert('出的牌必须大于上家');
            return;
        }
    }
    
    selected.forEach(card => {
        const index = gameState.players[0].findIndex(c => 
            c.suit === card.suit && c.value === card.value
        );
        if (index !== -1) {
            gameState.players[0].splice(index, 1);
        }
    });
    
    gameState.lastPlayedCards = selected;
    gameState.lastPlayer = 0;
    
    updateUI();
    
    if (gameState.players[0].length === 0) {
        endGame(0);
        return;
    }
    
    hidePlayButtons();
    nextPlayer();
}

function passPlay() {
    if (gameState.lastPlayer === 0) {
        alert('你是先手，必须出牌');
        return;
    }
    
    document.getElementById('myPlayedCards').innerHTML = '<span class="pass-text">不出</span>';
    hidePlayButtons();
    nextPlayer();
}

function hint() {
    const myCards = gameState.players[0];
    const lastCards = gameState.lastPlayedCards;
    const isNewRound = gameState.lastPlayer === 0 || gameState.lastPlayer === -1;
    
    const validCards = findValidPlay(myCards, lastCards, isNewRound);
    
    document.querySelectorAll('.card.selected').forEach(card => {
        card.classList.remove('selected');
    });
    
    if (validCards) {
        validCards.forEach(card => {
            document.querySelectorAll('#myCards .card').forEach(cardEl => {
                if (cardEl.dataset.suit === card.suit && cardEl.dataset.value === card.value) {
                    cardEl.classList.add('selected');
                }
            });
        });
    } else if (!isNewRound) {
        alert('没有能压过上家的牌');
    } else {
        const cardElements = document.querySelectorAll('#myCards .card');
        if (cardElements.length > 0) {
            cardElements[cardElements.length - 1].classList.add('selected');
        }
    }
}

function getSelectedCards() {
    const selected = [];
    document.querySelectorAll('#myCards .card.selected').forEach(cardEl => {
        const suit = cardEl.dataset.suit;
        const value = cardEl.dataset.value;
        selected.push({ suit, value, rank: parseInt(cardEl.dataset.rank) });
    });
    return selected;
}

// 获取牌型
function getCardType(cards) {
    const n = cards.length;
    if (n === 0) return null;
    
    const ranks = cards.map(c => c.rank).sort((a, b) => a - b);
    const countMap = {};
    ranks.forEach(r => countMap[r] = (countMap[r] || 0) + 1);
    const counts = Object.values(countMap).sort((a, b) => b - a);
    const uniqueRanks = Object.keys(countMap).map(Number).sort((a, b) => a - b);
    
    // 王炸
    if (n === 2 && ranks.includes(13) && ranks.includes(14)) {
        return { type: 'rocket', rank: 100 };
    }
    
    // 炸弹
    if (n === 4 && counts[0] === 4) {
        return { type: 'bomb', rank: ranks[0] };
    }
    
    // 单张
    if (n === 1) {
        return { type: 'single', rank: ranks[0] };
    }
    
    // 对子
    if (n === 2 && counts[0] === 2) {
        return { type: 'pair', rank: ranks[0] };
    }
    
    // 三张
    if (n === 3 && counts[0] === 3) {
        return { type: 'triple', rank: ranks[0] };
    }
    
    // 三带一
    if (n === 4 && counts[0] === 3) {
        const tripleRank = Object.keys(countMap).find(k => countMap[k] === 3);
        return { type: 'triple_one', rank: Number(tripleRank) };
    }
    
    // 三带二
    if (n === 5 && counts[0] === 3 && counts[1] === 2) {
        const tripleRank = Object.keys(countMap).find(k => countMap[k] === 3);
        return { type: 'triple_two', rank: Number(tripleRank) };
    }
    
    // 顺子（5张以上连续，不能有2和王）
    if (n >= 5 && counts.every(c => c === 1)) {
        if (ranks[n-1] <= 11 && isConsecutive(ranks)) {
            return { type: 'straight', rank: ranks[n-1], length: n };
        }
    }
    
    // 连对（3对以上连续）
    if (n >= 6 && n % 2 === 0 && counts.every(c => c === 2)) {
        if (uniqueRanks[uniqueRanks.length-1] <= 11 && isConsecutive(uniqueRanks)) {
            return { type: 'straight_pair', rank: uniqueRanks[uniqueRanks.length-1], length: n };
        }
    }
    
    // 飞机不带
    if (n >= 6 && n % 3 === 0 && counts.every(c => c === 3)) {
        if (uniqueRanks[uniqueRanks.length-1] <= 11 && isConsecutive(uniqueRanks)) {
            return { type: 'plane', rank: uniqueRanks[uniqueRanks.length-1], length: n };
        }
    }
    
    // 飞机带单
    if (n >= 8 && n % 4 === 0 && counts[0] === 3) {
        const triples = Object.keys(countMap).filter(k => countMap[k] === 3).map(Number).sort((a, b) => a - b);
        if (triples.length >= 2 && triples[triples.length-1] <= 11 && isConsecutive(triples)) {
            return { type: 'plane_single', rank: triples[triples.length-1], length: triples.length * 3 };
        }
    }
    
    // 飞机带对
    if (n >= 10 && n % 5 === 0 && counts[0] === 3) {
        const triples = Object.keys(countMap).filter(k => countMap[k] === 3).map(Number).sort((a, b) => a - b);
        const pairs = Object.keys(countMap).filter(k => countMap[k] === 2);
        if (triples.length >= 2 && pairs.length === triples.length && triples[triples.length-1] <= 11 && isConsecutive(triples)) {
            return { type: 'plane_pair', rank: triples[triples.length-1], length: triples.length * 3 };
        }
    }
    
    // 四带二单
    if (n === 6 && counts[0] === 4) {
        const fourRank = Object.keys(countMap).find(k => countMap[k] === 4);
        return { type: 'four_two_single', rank: Number(fourRank) };
    }
    
    // 四带二对
    if (n === 8 && counts[0] === 4 && counts.filter(c => c === 2).length === 2) {
        const fourRank = Object.keys(countMap).find(k => countMap[k] === 4);
        return { type: 'four_two_pair', rank: Number(fourRank) };
    }
    
    return null;
}

// 检查是否连续
function isConsecutive(ranks) {
    for (let i = 1; i < ranks.length; i++) {
        if (ranks[i] - ranks[i-1] !== 1) return false;
    }
    return true;
}

// 比较牌型
function canBeat(type1, type2) {
    // 王炸最大
    if (type1.type === 'rocket') return true;
    if (type2.type === 'rocket') return false;
    
    // 炸弹大于非炸弹
    if (type1.type === 'bomb' && type2.type !== 'bomb') return true;
    if (type2.type === 'bomb' && type1.type !== 'bomb') return false;
    
    // 同类型比较
    if (type1.type !== type2.type) return false;
    
    // 顺子、连对、飞机需要长度相同
    if (['straight', 'straight_pair', 'plane', 'plane_single', 'plane_pair'].includes(type1.type)) {
        if (type1.length !== type2.length) return false;
    }
    
    return type1.rank > type2.rank;
}

function isValidPlay(cards, lastCards) {
    const currentType = getCardType(cards);
    if (!currentType) return false;
    
    // 先手任意合法牌型都可以
    if (!lastCards || lastCards.length === 0) return true;
    
    const lastType = getCardType(lastCards);
    return canBeat(currentType, lastType);
}

function computerPlay() {
    setTimeout(() => {
        const playerIndex = gameState.currentPlayer;
        const cards = gameState.players[playerIndex];
        
        if (cards.length > 0) {
            const playedCards = findValidPlay(cards, gameState.lastPlayedCards, gameState.lastPlayer === playerIndex);
            
            if (playedCards) {
                playedCards.forEach(card => {
                    const index = cards.findIndex(c => c.suit === card.suit && c.value === card.value);
                    if (index !== -1) cards.splice(index, 1);
                });
                
                gameState.lastPlayedCards = playedCards;
                gameState.lastPlayer = playerIndex;
                
                renderComputerPlayedCards(playerIndex, playedCards);
            } else {
                renderComputerPlayedCards(playerIndex, null);
            }
        }
        
        updateUI();
        
        if (cards.length === 0) {
            endGame(playerIndex);
            return;
        }
        
        nextPlayer();
    }, 1000);
}

function findValidPlay(cards, lastCards, isNewRound) {
    if (isNewRound || !lastCards || lastCards.length === 0) {
        const type = findSmallestType(cards);
        if (type) return type;
        return [cards[cards.length - 1]];
    }
    
    const lastType = getCardType(lastCards);
    if (!lastType) return null;
    
    if (lastType.type === 'single') {
        for (let i = cards.length - 1; i >= 0; i--) {
            if (cards[i].rank > lastType.rank) return [cards[i]];
        }
    }
    
    if (lastType.type === 'pair') {
        for (let i = cards.length - 1; i >= 1; i--) {
            if (cards[i].rank === cards[i-1].rank && cards[i].rank > lastType.rank) return [cards[i], cards[i-1]];
        }
    }
    
    if (lastType.type === 'triple') {
        const triple = findTriple(cards, lastType.rank);
        if (triple) return triple;
    }
    
    if (lastType.type === 'triple_one') {
        const triple = findTriple(cards, lastType.rank);
        if (triple && cards.length > 3) {
            const single = cards.find(c => !triple.includes(c));
            if (single) return [...triple, single];
        }
    }
    
    if (lastType.type === 'triple_two') {
        const triple = findTriple(cards, lastType.rank);
        const pair = findPair(cards, -1);
        if (triple && pair && !triple.includes(pair[0])) return [...triple, ...pair];
    }
    
    if (lastType.type !== 'bomb' && lastType.type !== 'rocket') {
        const bomb = findBomb(cards, -1);
        if (bomb) return bomb;
    }
    
    if (lastType.type === 'bomb') {
        const bomb = findBomb(cards, lastType.rank);
        if (bomb) return bomb;
    }
    
    if (lastType.type !== 'rocket') {
        const rocket = findRocket(cards);
        if (rocket) return rocket;
    }
    
    return null;
}

function findSmallestType(cards) {
    if (cards.length > 0) return [cards[cards.length - 1]];
    return null;
}

function findTriple(cards, minRank) {
    for (let i = 0; i < cards.length - 2; i++) {
        if (cards[i].rank === cards[i+1].rank && cards[i].rank === cards[i+2].rank && cards[i].rank > minRank) {
            return [cards[i], cards[i+1], cards[i+2]];
        }
    }
    return null;
}

function findPair(cards, minRank) {
    for (let i = 0; i < cards.length - 1; i++) {
        if (cards[i].rank === cards[i+1].rank && cards[i].rank > minRank) return [cards[i], cards[i+1]];
    }
    return null;
}

function findBomb(cards, minRank) {
    for (let i = 0; i < cards.length - 3; i++) {
        if (cards[i].rank === cards[i+1].rank && cards[i].rank === cards[i+2].rank && cards[i].rank === cards[i+3].rank && cards[i].rank > minRank) {
            return [cards[i], cards[i+1], cards[i+2], cards[i+3]];
        }
    }
    return null;
}

function findRocket(cards) {
    const smallJoker = cards.find(c => c.rank === 13);
    const bigJoker = cards.find(c => c.rank === 14);
    if (smallJoker && bigJoker) return [smallJoker, bigJoker];
    return null;
}

function renderComputerPlayedCards(playerIndex, cards) {
    const selectors = ['.left-player .played-cards', '.top-player .played-cards', '.right-player .played-cards'];
    const container = document.querySelector(selectors[playerIndex - 1]);
    
    if (!container) return;
    
    if (!cards) {
        container.innerHTML = '<span class="pass-text">不出</span>';
        return;
    }
    
    container.innerHTML = '';
    cards.forEach(card => {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        cardEl.style.margin = '0 2px';
        
        const isRed = card.suit === '\u2665' || card.suit === '\u2666';
        cardEl.style.color = isRed ? '#e74c3c' : '#2c3e50';
        
        cardEl.innerHTML = `
            <div class="card-value">${card.value}</div>
            <div class="card-suit">${card.suit}</div>
        `;
        
        container.appendChild(cardEl);
    });
}

function nextPlayer() {
    gameState.currentPlayer = (gameState.currentPlayer + 1) % 4;
    
    if (gameState.currentPlayer === 0) {
        showPlayButtons();
    } else {
        computerPlay();
    }
}

function endGame(winner) {
    const winnerText = winner === 0 ? '你赢了！' : `电脑${winner}赢了！`;
    document.getElementById('gameStatus').textContent = winnerText;
    document.getElementById('btnStart').style.display = 'inline-block';
    hidePlayButtons();
}

function hidePlayButtons() {
    document.getElementById('btnPlay').style.display = 'none';
    document.getElementById('btnPass').style.display = 'none';
    document.getElementById('btnHint').style.display = 'none';
}

function updateUI() {
    renderMyCards();
    
    document.querySelector('.left-player .card-count').textContent = gameState.players[1].length + '张';
    document.querySelector('.top-player .card-count').textContent = gameState.players[2].length + '张';
    document.querySelector('.right-player .card-count').textContent = gameState.players[3].length + '张';
    document.getElementById('myCardCount').textContent = gameState.players[0].length + '张';
    
    renderBottomCards();
}

function renderMyCards() {
    const container = document.getElementById('myCards');
    container.innerHTML = '';
    
    gameState.players[0].forEach(card => {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        cardEl.dataset.suit = card.suit;
        cardEl.dataset.value = card.value;
        cardEl.dataset.rank = card.rank;
        
        const isRed = card.suit === '\u2665' || card.suit === '\u2666';
        cardEl.style.color = isRed ? '#e74c3c' : '#2c3e50';
        
        cardEl.innerHTML = `
            <div class="card-value">${card.value}</div>
            <div class="card-suit">${card.suit}</div>
        `;
        
        cardEl.addEventListener('click', () => {
            cardEl.classList.toggle('selected');
        });
        
        container.appendChild(cardEl);
    });
}

function renderBottomCards() {
    const container = document.getElementById('bottomCards');
    container.innerHTML = '';
    
    gameState.bottomCards.forEach(card => {
        const cardEl = document.createElement('div');
        cardEl.className = 'card small';
        
        const isRed = card.suit === '\u2665' || card.suit === '\u2666';
        cardEl.style.color = isRed ? '#e74c3c' : '#2c3e50';
        
        cardEl.innerHTML = `
            <div class="card-value">${card.value}</div>
            <div class="card-suit">${card.suit}</div>
        `;
        
        container.appendChild(cardEl);
    });
}