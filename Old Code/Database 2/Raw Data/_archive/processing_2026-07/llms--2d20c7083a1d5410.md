# LLMs+

![rw-book-cover](https://www.technologyreview.com/static/media/favicon.1cfcdb44759a0f93ddf5feb5405dd4cc.ico)

## Metadata
- Author: [[Will Douglas Heaven]]
- Full Title: LLMs+
- Category: #articles
- Summary: Large language models (LLMs) like ChatGPT are improving to become cheaper, faster, and better at solving complex problems. New methods, such as splitting tasks among expert parts or using different neural networks, help make LLMs more efficient. Researchers are also finding ways to handle much larger amounts of information without losing focus, allowing LLMs to work on harder, longer tasks reliably.
- URL: https://www.technologyreview.com/2026/04/21/1135645/llm-large-language-models-ai/

## Full Document
LLMs are evolving. The next generation of the world’s hottest technology will be cheaper, more efficient, and able to solve bigger problems without going off the rails.

![](https://wp.technologyreview.com/wp-content/uploads/2026/04/llm-plusC.jpg?fit=19998,1958)
Stephanie Arnett/MIT Technology Review | Adobe Stock

When ChatGPT launched as an experimental prototype in late 2022, OpenAI’s chatbot became an everyday everything app for hundreds of millions of people. LLMs like ChatGPT were the new future: The entire tech industry was consumed by the inferno, with companies racing to spin up rival products.

The ashes of the old tech world still haven’t settled, but that hasn’t stopped people from asking what’s next. Spoiler alert: The next big thing after LLMs is more LLMs. But better. Let’s call them LLMs+.

The challenge is to get LLMs to work through complex and multipart problems that would take humans days or weeks to solve. If they are going to help us tackle some of our hardest challenges (which is the stated aim of the top labs), then they need to be able to work by themselves for longer periods of time.

To get there, a few things need to happen. First, LLMs must become more efficient and cheaper to run. Some of the biggest advances are on this front. One approach, called mixture-of-experts, splits an LLM up into smaller parts and gives each an expertise in a different type of task. That means only some parts of the model need to be switched on at a given time.

Another way to make LLMs more efficient could be to ditch transformers—the type of neural network underpinning almost all of them today—in favor of diffusion models, an alternative type of neural network more typically used for image and video generation. There are more experimental approaches, too. Last year, the Chinese AI firm [DeepSeek showed off a way to encode text in images](https://www.technologyreview.com/2025/10/29/1126932/deepseek-ocr-visual-compression/), which cuts computation costs.

Another crucial area of progress has to do with what’s known as an LLM’s context window. This is the amount of text (or video) that a model can take in at once, equivalent to its working memory. A couple of years ago, LLMs could process several thousand tokens (words or parts of words) in one go, or a few dozen pages of text. The latest models now have context windows up to a million tokens long—a whole stack of books. But the bigger the context window and the longer the task, the more likely models are to go off the rails or forget what they were doing. There are breakthroughs happening there, too. One recent paper by researchers at MIT CSAIL introduced what they call [recursive LLMs](https://arxiv.org/abs/2512.24601). Instead of taking in a vast context window at once, recursive LLMs break their input up into chunks and send each chunk to a copy of itself, which in turn might break those chunks up again and send the results to even more copies. Multiple LLMs processing smaller pieces of information seem to be far more reliable for long, hard tasks. The result is an LLM, but not as we know it.
