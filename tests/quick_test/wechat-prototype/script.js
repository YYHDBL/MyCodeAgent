// 聊天数据存储
const chatData = {
    '张三': [
        { type: 'received', content: '你好，最近怎么样？', time: '10:30' },
        { type: 'sent', content: '挺好的，你呢？', time: '10:31' },
        { type: 'received', content: '我也不错，周末有空出来聚聚吗？', time: '10:32' },
        { type: 'sent', content: '好啊，去哪里？', time: '10:33' }
    ],
    '李四': [
        { type: 'received', content: '明天有空吗？', time: '昨天' }
    ],
    '工作群': [
        { type: 'received', content: '大家注意，明天会议改到下午2点', time: '周一' },
        { type: 'received', content: '收到', time: '周一' },
        { type: 'sent', content: '好的，知道了', time: '周一' }
    ],
    '王五': [
        { type: 'sent', content: '文件已经发送给你了', time: '周日' },
        { type: 'received', content: '好的，收到', time: '周日' }
    ]
};

// 当前选中的联系人
let currentContact = '张三';

// DOM元素
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const contactItems = document.querySelectorAll('.contact-item');
const chatTitle = document.querySelector('.chat-title');
const emojiBtn = document.getElementById('emojiBtn');
const emojiPicker = document.getElementById('emojiPicker');
const imageBtn = document.getElementById('imageBtn');
const imageInput = document.getElementById('imageInput');
const fileBtn = document.getElementById('fileBtn');
const fileInput = document.getElementById('fileInput');
const userAvatar = document.getElementById('userAvatar');
const avatarInput = document.getElementById('avatarInput');

// 初始化
function init() {
    // 绑定联系人点击事件
    contactItems.forEach(item => {
        item.addEventListener('click', () => {
            const contactName = item.dataset.contact;
            switchContact(contactName);
        });
    });

    // 绑定发送按钮事件
    sendBtn.addEventListener('click', sendMessage);

    // 绑定回车发送事件
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // 绑定emoji按钮事件
    emojiBtn.addEventListener('click', toggleEmojiPicker);

    // 绑定emoji点击事件
    document.querySelectorAll('.emoji-item').forEach(emoji => {
        emoji.addEventListener('click', () => {
            insertEmoji(emoji.textContent);
        });
    });

    // 绑定图片按钮事件
    imageBtn.addEventListener('click', () => {
        imageInput.click();
    });

    // 绑定图片上传事件
    imageInput.addEventListener('change', handleImageUpload);

    // 绑定文件按钮事件
    fileBtn.addEventListener('click', () => {
        fileInput.click();
    });

    // 绑定文件上传事件
    fileInput.addEventListener('change', handleFileUpload);

    // 绑定头像更换事件
    userAvatar.addEventListener('click', () => {
        avatarInput.click();
    });

    // 绑定头像文件选择事件
    avatarInput.addEventListener('change', handleAvatarChange);

    // 绑定删除好友按钮事件
    document.querySelectorAll('.delete-friend-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const contactItem = btn.closest('.contact-item');
            const contactName = contactItem.dataset.contact;
            deleteFriend(contactName, contactItem);
        });
    });

    // 点击其他地方关闭emoji选择器
    document.addEventListener('click', (e) => {
        if (!emojiPicker.contains(e.target) && e.target !== emojiBtn) {
            emojiPicker.style.display = 'none';
        }
    });

    // 滚动到底部
    scrollToBottom();
}

// 切换联系人
function switchContact(contactName) {
    currentContact = contactName;
    
    // 更新联系人选中状态
    contactItems.forEach(item => {
        if (item.dataset.contact === contactName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // 更新聊天标题
    chatTitle.textContent = contactName;

    // 重新加载消息
    loadMessages();
}

// 加载消息
function loadMessages() {
    const messages = chatData[currentContact] || [];
    chatMessages.innerHTML = '';

    messages.forEach(msg => {
        if (msg.isImage) {
            appendImageMessage(msg.type, msg.content, msg.time);
        } else if (msg.isFile) {
            appendFileMessage(msg.type, msg.fileName, msg.fileSize, msg.time);
        } else {
            appendMessage(msg.type, msg.content, msg.time);
        }
    });

    scrollToBottom();
}

// 添加消息到界面
function appendMessage(type, content, time) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    if (type === 'received') {
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = currentContact.charAt(0);
        messageDiv.appendChild(avatar);
    }

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    const messageBubble = document.createElement('div');
    messageBubble.className = 'message-bubble';
    messageBubble.textContent = content;

    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = time;

    messageContent.appendChild(messageBubble);
    messageContent.appendChild(messageTime);
    messageDiv.appendChild(messageContent);

    chatMessages.appendChild(messageDiv);
}

// 发送消息
function sendMessage() {
    const content = messageInput.value.trim();
    if (!content) return;

    // 获取当前时间
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    // 添加消息到界面
    appendMessage('sent', content, time);

    // 保存到数据
    if (!chatData[currentContact]) {
        chatData[currentContact] = [];
    }
    chatData[currentContact].push({
        type: 'sent',
        content: content,
        time: time
    });

    // 更新联系人列表的最后一条消息
    updateLastMessage(currentContact, content, time);

    // 清空输入框
    messageInput.value = '';

    // 滚动到底部
    scrollToBottom();

    // 模拟自动回复
    setTimeout(() => {
        simulateReply();
    }, 1000 + Math.random() * 2000);
}

// 模拟自动回复
function simulateReply() {
    const replies = [
        '好的，收到！',
        '没问题！',
        '我知道了',
        '好的，明白了',
        '😊',
        '好的，稍等一下',
        '明白了，谢谢！',
        '好的，我看看',
        '可以',
        '好的'
    ];

    const randomReply = replies[Math.floor(Math.random() * replies.length)];
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    // 添加回复到界面
    appendMessage('received', randomReply, time);

    // 保存到数据
    if (!chatData[currentContact]) {
        chatData[currentContact] = [];
    }
    chatData[currentContact].push({
        type: 'received',
        content: randomReply,
        time: time
    });

    // 更新联系人列表的最后一条消息
    updateLastMessage(currentContact, randomReply, time);

    // 滚动到底部
    scrollToBottom();
}

// 更新联系人列表的最后一条消息
function updateLastMessage(contactName, content, time) {
    const contactItem = document.querySelector(`.contact-item[data-contact="${contactName}"]`);
    if (contactItem) {
        const lastMessage = contactItem.querySelector('.last-message');
        const contactTime = contactItem.querySelector('.contact-time');
        
        if (lastMessage) {
            lastMessage.textContent = content;
        }
        if (contactTime) {
            contactTime.textContent = time;
        }
    }
}

// 滚动到底部
function scrollToBottom() {
    setTimeout(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 100);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 切换emoji选择器
function toggleEmojiPicker() {
    if (emojiPicker.style.display === 'none') {
        emojiPicker.style.display = 'block';
    } else {
        emojiPicker.style.display = 'none';
    }
}

// 插入emoji到输入框
function insertEmoji(emoji) {
    messageInput.value += emoji;
    messageInput.focus();
    emojiPicker.style.display = 'none';
}

// 处理图片上传
function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(event) {
        const imageDataUrl = event.target.result;
        
        // 获取当前时间
        const now = new Date();
        const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

        // 添加图片消息到界面
        appendImageMessage('sent', imageDataUrl, time);

        // 保存到数据
        if (!chatData[currentContact]) {
            chatData[currentContact] = [];
        }
        chatData[currentContact].push({
            type: 'sent',
            content: imageDataUrl,
            isImage: true,
            time: time
        });

        // 更新联系人列表的最后一条消息
        updateLastMessage(currentContact, '[图片]', time);

        // 滚动到底部
        scrollToBottom();

        // 模拟自动回复
        setTimeout(() => {
            simulateReply();
        }, 1000 + Math.random() * 2000);
    };
    reader.readAsDataURL(file);

    // 清空input以便重复上传同一文件
    imageInput.value = '';
}

// 添加图片消息到界面
function appendImageMessage(type, imageDataUrl, time) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    if (type === 'received') {
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = currentContact.charAt(0);
        messageDiv.appendChild(avatar);
    }

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    const messageBubble = document.createElement('div');
    messageBubble.className = 'message-bubble';
    
    const img = document.createElement('img');
    img.src = imageDataUrl;
    img.className = 'message-image';
    img.alt = '图片';
    messageBubble.appendChild(img);

    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = time;

    messageContent.appendChild(messageBubble);
    messageContent.appendChild(messageTime);
    messageDiv.appendChild(messageContent);

    chatMessages.appendChild(messageDiv);
}

// 处理头像更换
function handleAvatarChange(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(event) {
        const imageDataUrl = event.target.result;
        userAvatar.style.backgroundImage = `url(${imageDataUrl})`;
        userAvatar.style.backgroundSize = 'cover';
        userAvatar.style.backgroundPosition = 'center';
        userAvatar.textContent = '';
    };
    reader.readAsDataURL(file);

    // 清空input以便重复上传同一文件
    avatarInput.value = '';
}

// 删除好友
function deleteFriend(contactName, contactItem) {
    // 确认删除
    if (!confirm(`确定要删除好友 "${contactName}" 吗？`)) {
        return;
    }

    // 从数据中删除
    delete chatData[contactName];

    // 从界面中移除联系人项
    contactItem.remove();

    // 如果删除的是当前选中的联系人
    if (currentContact === contactName) {
        // 清空聊天窗口
        chatMessages.innerHTML = '';
        chatTitle.textContent = '';

        // 尝试切换到第一个联系人
        const remainingContacts = document.querySelectorAll('.contact-item');
        if (remainingContacts.length > 0) {
            const firstContact = remainingContacts[0];
            const firstContactName = firstContact.dataset.contact;
            switchContact(firstContactName);
        } else {
            currentContact = '';
        }
    }

    // 更新联系人列表引用
    const updatedContactItems = document.querySelectorAll('.contact-item');
}
