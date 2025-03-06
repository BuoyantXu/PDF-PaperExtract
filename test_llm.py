import base64

from openai import OpenAI


#  Base64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


clients = {
    "aliyun": OpenAI(
        api_key="***",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "siliconflow": OpenAI(
        api_key="***",
        base_url="https://api.siliconflow.cn/v1",
    )
}


def Qwen_VL_extract(image_path, model="qwen-omni-turbo", prompt=None, base="aliyun"):
    image = encode_image(image_path)
    client = clients[base]

    if prompt is None:
        prompt = "请帮我将图像中的表格整理为markdown格式"
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": [{
                    "type": "text",
                    "text": "你是一个学术期刊编辑，擅长整理期刊论文中的图像表格格式。"}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        # 设置输出数据的模态，当前支持["text"]
        modalities=["text"],
        # stream 必须设置为 True，否则会报错
        stream=True,
        stream_options={"include_usage": True},
    )

    response = []
    for chunk in completion:
        if chunk.choices:
            response.append(chunk.choices[0].delta)

    text_md = "".join([t.content for t in response if t.content])
    print(text_md)

    return text_md


if __name__ == "__main__":
    from prompts import prompt_table_correction
    import pickle

    with open("tables.pkl", "rb") as f:
        tables = pickle.load(f)

    i = 16
    image_path, table_markdown = tables[i]['image_path'], tables[i]['table_markdown']

    # 打开图像
    from PIL import Image

    image = Image.open(image_path)
    image.show()
    print(table_markdown)
    prompt = prompt_table_correction(table_str=table_markdown)

    # res = Qwen_VL_extract(image_path, prompt=prompt, base="aliyun")
    # res = Qwen_VL_extract(image_path, prompt=prompt, model="Qwen/Qwen2-VL-72B-Instruct", base="siliconflow")

    res = Qwen_VL_extract(image_path, prompt=prompt, model="Pro/Qwen/Qwen2-VL-7B-Instruct", base="siliconflow")

    print("\n\n---------------------------------------------------------\n\n")
    print(res)
