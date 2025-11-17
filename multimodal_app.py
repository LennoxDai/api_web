import streamlit as st
import base64
from openai import OpenAI
import io
from PIL import Image
import uuid # 用于生成唯一的会话ID

# --- 配置 ---
# 请替换为您实际的中转服务器地址
CUSTOM_BASE_URL = "http://35.220.164.252:3888/v1/" 
# 请替换为您实际的中转 API Key
CUSTOM_API_KEY = "sk-nxgISKqFUvLMIttLw3jEiJAOUwTsXBuoomPERn35e9vQigQG"  
# 使用指定的模型名称
MODEL_NAME = "gpt-5.1-2025-11-13" 

# 初始化 OpenAI 客户端
# 使用 st.cache_resource 确保客户端只初始化一次
@st.cache_resource
def get_openai_client(base_url: str, api_key: str):
    """创建并返回 OpenAI 客户端实例"""
    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        return client
    except Exception as e:
        st.error(f"初始化 OpenAI 客户端失败: {e}")
        st.stop()
        
client = get_openai_client(CUSTOM_BASE_URL, CUSTOM_API_KEY)


# --- 辅助函数 ---

def image_to_base64(image_file):
    """将上传的图片文件转换为 Base64 编码的字符串和 MIME 类型"""
    # 逻辑与前一版本相同，用于处理图片编码
    if image_file is not None:
        try:
            bytes_data = image_file.read()
            image = Image.open(io.BytesIO(bytes_data))
            
            buffered = io.BytesIO()
            format = image.format if image.format else 'JPEG'
            if format.upper() not in ('JPEG', 'PNG'):
                format = 'JPEG'
            image.save(buffered, format=format)
            
            base64_string = base64.b64encode(buffered.getvalue()).decode("utf-8")
            mime_type = f"image/{format.lower()}"
            return base64_string, mime_type
        except Exception as e:
            st.error(f"处理图片失败: {e}")
            return None, None
    return None, None


def generate_content_payload(text_prompt, image_files):
    """根据文字和图片生成 API 调用所需的 content 列表"""
    content = []
    
    # 1. 添加图片内容
    for img_file in image_files:
        base64_str, mime_type = image_to_base64(img_file)
        if base64_str and mime_type:
            # 倒带文件指针，确保 Streamlit 可以显示图片或再次读取
            img_file.seek(0) 
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_str}"
                }
            })
        
    # 2. 添加文字提示
    if text_prompt.strip():
        content.append({
            "type": "text",
            "text": text_prompt
        })

    return content


def get_current_chat_history():
    """获取当前会话的聊天历史，如果不存在则初始化"""
    chat_id = st.session_state.current_chat_id
    if chat_id not in st.session_state.chats:
        st.session_state.chats[chat_id] = []
    return st.session_state.chats[chat_id]


def create_new_chat():
    """创建一个新的会话"""
    new_id = str(uuid.uuid4())
    st.session_state.current_chat_id = new_id
    st.session_state.chats[new_id] = []
    st.session_state.chat_names[new_id] = f"新会话 {len(st.session_state.chat_names) + 1}"
    st.rerun() # 重新运行以切换到新会话


def handle_api_call(user_prompt, uploaded_files):
    """处理 API 调用和结果展示"""
    
    chat_history = get_current_chat_history()
    
    # 1. 准备 API 负载
    content_payload = generate_content_payload(user_prompt, uploaded_files)
    
    # 将用户输入添加到历史记录
    user_message = {"role": "user", "content": content_payload}
    chat_history.append(user_message)
    
    # 2. 准备发送给 API 的消息列表
    # API 消息格式需要是 [{'role': 'user', 'content': [...]}, {'role': 'assistant', 'content': '...'}]
    api_messages = [
        # 对于历史消息，如果 content 是列表，需要检查其结构是否符合API要求
        # 简化处理：API 仅使用文本历史作为上下文
        {"role": msg["role"], "content": msg["content"]}
        for msg in chat_history if msg["role"] == "user" or (msg["role"] == "assistant" and isinstance(msg["content"], str))
    ]
    
    # 在聊天界面添加一个临时的 AI 占位符
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # 3. 调用 API
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=api_messages, # 使用完整的历史记录作为上下文
                stream=True,
            )

            # 4. 处理流式回复
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")

            # 最终显示完整回复
            message_placeholder.markdown(full_response)
            
            # 将 AI 回复添加到历史记录
            ai_message = {"role": "assistant", "content": full_response}
            chat_history.append(ai_message)

        except Exception as e:
            error_message = f"API 调用失败: {e}"
            message_placeholder.error(error_message)
            # 如果失败，将用户消息从历史记录中移除，避免污染
            chat_history.pop()


# --- Streamlit 页面初始化 ---

st.set_page_config(
    page_title="多会话多模态 AI 聊天", 
    layout="wide"
)

# 初始化 Session State
if "chats" not in st.session_state:
    st.session_state.chats = {} # 存储所有会话的历史记录: {chat_id: [{"role": "user", "content": [...]}, ...]}
if "chat_names" not in st.session_state:
    st.session_state.chat_names = {} # 存储会话名称: {chat_id: "会话名称"}
if "current_chat_id" not in st.session_state:
    # 首次加载时创建一个默认会话
    create_new_chat()


# --- 侧边栏：会话管理 ---
with st.sidebar:
    st.title("📂 对话会话")
    
    # 创建新会话按钮
    if st.button("✨ 创建新会话", use_container_width=True):
        create_new_chat()
        
    st.markdown("---")
    
    # 会话列表
    st.subheader("历史会话")
    # 确保只显示有效的会话ID
    valid_chat_ids = [id for id in st.session_state.chat_names if id in st.session_state.chats]
    
    for chat_id in valid_chat_ids:
        chat_name = st.session_state.chat_names.get(chat_id, "未知会话")
        
        # 突出显示当前会话
        is_current = chat_id == st.session_state.current_chat_id
        
        if st.button(chat_name, key=f"chat_btn_{chat_id}", use_container_width=True, type="primary" if is_current else "secondary"):
            st.session_state.current_chat_id = chat_id
            st.rerun() # 切换会话


# --- 主应用区 ---

current_chat_id = st.session_state.current_chat_id
current_chat_name = st.session_state.chat_names.get(current_chat_id, "未知会话")
st.header(f"💬 当前会话: **{current_chat_name}**")

# 显示聊天历史
chat_history = get_current_chat_history()

# 使用容器来创建可滚动的聊天区域
chat_container = st.container(height=550)

with chat_container:
    for message in chat_history:
        # 使用 Streamlit 的 chat_message API
        with st.chat_message(message["role"]):
            content = message["content"]
            
            if message["role"] == "user":
                # 区分文字和图片
                text_parts = [part["text"] for part in content if part["type"] == "text"]
                image_parts = [part for part in content if part["type"] == "image_url"]
                
                # 显示文字
                if text_parts:
                    st.markdown(text_parts[0])
                    
                # 显示图片 (在 Streamlit 中，图片 URL 无法直接渲染，我们只能在上传时显示，或者在发送消息时手动渲染)
                # 由于历史记录中的图片是 base64 URL，为了简化，我们仅在用户发送时显示预览，并在历史中用文字描述。
                if image_parts:
                    st.info(f"（此消息包含 {len(image_parts)} 张图片附件）")
            
            elif message["role"] == "assistant":
                # AI 回复直接是字符串
                st.markdown(content)


# --- 输入区域 (底部) ---

# 使用 st.form 来确保输入框和图片上传不会在每次按键时触发重载
with st.form(key='chat_form', clear_on_submit=True):
    # 1. 图片上传
    uploaded_files = st.file_uploader(
        "上传图片 (最多 5 张)", 
        type=["jpg", "jpeg", "png"], 
        accept_multiple_files=True,
        key="uploader_input"
    )

    # 2. 文本输入
    col1, col2 = st.columns([8, 1])
    
    with col1:
        prompt = st.text_input(
            "输入您的消息...",
            key="text_input_prompt",
            placeholder="输入文字并可选上传图片..."
        )
        
    with col2:
        # 3. 发送按钮
        submit_button = st.form_submit_button("发送 🚀", type="primary")

# 处理提交
if submit_button and (prompt or uploaded_files):
    if not prompt.strip() and not uploaded_files:
        # 只有在表单提交时才检查，但由于 form_submit_button 已经包含在 form 中，我们只需处理非空情况
        pass 
    else:
        # 确保图片文件数量限制
        files_to_send = uploaded_files[:5] if uploaded_files else []
        
        # 将用户输入添加到历史记录并触发 API 调用
        handle_api_call(prompt, files_to_send)
        
        # 重新运行以更新聊天历史
        st.rerun()