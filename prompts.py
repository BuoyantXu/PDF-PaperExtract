import base64


#  Base64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def prompt_table_correction(table_str: str, table_format='markdown') -> str:
    prompt = f"""下面是我从pdf中提取的表格并转换成{table_format}格式后的结果，但可能存在问题。
请帮我遵循图像中的表格格式进行修正，例如处理多行表头，修正行列划分，删除错误字符。
注意不要丢失任何信息，只需对表格进行修正。
仅输出提取的{table_format}结果不需要进行解释。

```{table_format}
{table_str}
```"""
    return prompt
