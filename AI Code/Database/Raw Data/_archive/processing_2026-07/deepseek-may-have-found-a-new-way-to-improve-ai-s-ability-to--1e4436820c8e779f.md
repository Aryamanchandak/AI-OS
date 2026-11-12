# DeepSeek May Have Found a New Way to Improve AI’s Ability to Remember

![rw-book-cover](https://www.technologyreview.com/static/media/favicon.1cfcdb44759a0f93ddf5feb5405dd4cc.ico)

## Metadata
- Author: [[Caiwei Chen]]
- Full Title: DeepSeek May Have Found a New Way to Improve AI’s Ability to Remember
- Category: #articles
- Summary: Chinese AI company DeepSeek made an OCR model that stores text as images instead of text tokens.  
This image-based method lets models remember more with far fewer tokens, cutting compute and energy needs.  
Researchers say it could improve AI memory and help build more efficient, longer-lasting agents.
- URL: https://www.technologyreview.com/2025/10/29/1126932/deepseek-ocr-visual-compression/

## Full Document
Instead of using text tokens, the Chinese AI company is packing information into images.

![square patches of document fragments](https://wp.technologyreview.com/wp-content/uploads/2025/10/ocr-patches2.jpg?fit=2252,1266)square patches of document fragments
EXECUTIVE SUMMARY

An AI model released by the Chinese AI company DeepSeek uses new techniques that could significantly improve AI’s ability to “remember.”

Released last week, the optical character recognition (OCR) model works by extracting text from an image and turning it into machine-readable words. This is the same technology that powers scanner apps, translation of text in photos, and many accessibility tools.

OCR is already a mature field with numerous high-performing systems, and according to the paper and some early reviews, DeepSeek’s new model performs on par with top models on key benchmarks.

But researchers say the model’s main innovation lies in how it processes information—specifically, how it stores and retrieves memories. Improving how AI models “remember” information could reduce the computing power they need to run, thus mitigating AI’s large [(and growing)](https://www.technologyreview.com/2025/05/20/1116327/ai-energy-usage-climate-footprint-big-tech) carbon footprint.

Currently, most large language models break text down into thousands of tiny units called tokens. This turns the text into representations that models can understand. However, these tokens quickly become expensive to store and compute with as conversations with end users grow longer. When a user chats with an AI for lengthy periods, this challenge can cause the AI to forget things it’s been told and get information muddled, a problem some call “context rot.”

The new methods developed by DeepSeek (and published in its [latest paper](https://github.com/deepseek-ai/DeepSeek-OCR/tree/main)) could help to overcome this issue. Instead of storing words as tokens, its system packs written information into image form, almost as if it’s taking a picture of pages from a book. This allows the model to retain nearly the same information while using far fewer tokens, the researchers found.

Essentially, the OCR model is a test bed for these new methods that permit more information to be packed into AI models more efficiently.

Besides using visual tokens instead of just text tokens, the model is built on a type of tiered compression that is not unlike how human memories fade: Older or less critical content is stored in a slightly more blurry form in order to save space. Despite that, the paper’s authors argue, this compressed content can still remain accessible in the background while maintaining a high level of system efficiency.

Text tokens have long been the default building block in AI systems. Using visual tokens instead is unconventional, and as a result, DeepSeek’s model is quickly capturing researchers’ attention. Andrej Karpathy, the former Tesla AI chief and a founding member of OpenAI, praised the paper on [X](https://x.com/karpathy/status/1980397031542989305), saying that images may ultimately be better than text as inputs for LLMs. Text tokens might be “wasteful and just terrible at the input,” he wrote.

Manling Li, an assistant professor of computer science at Northwestern University, says the paper offers a new framework for addressing the existing challenges in AI memory. “While the idea of using image-based tokens for context storage isn’t entirely new, this is the first study I’ve seen that takes it this far and shows it might actually work,” Li says.

Ask AI

Why it matters to you?BETA

Here’s why this story might matter to you, according to AI. This is a beta feature and AI hallucinates—it might get weird

An industry I care about is.

Tell me why it matters

[Learn more about how we're using AI.](https://www.technologyreview.com/how-we-use-ai/)

The method could open up new possibilities in AI research and applications, especially in creating more useful AI agents, says Zihan Wang, a PhD candidate at Northwestern University. He believes that since conversations with AI are continuous, this approach could help models remember more and assist users more effectively.

The technique can also be used to produce more training data for AI models. Model developers are currently grappling with a severe shortage of quality text to train systems on. But the DeepSeek paper says that the company’s OCR system can generate over 200,000 pages of training data a day on a single GPU.

The model and paper, however, are only an early exploration of using image tokens rather than text tokens for AI memorization. Li says she hopes to see visual tokens applied not just to memory storage but also to reasoning. Future work, she says, should explore how to make AI’s memory fade in a more dynamic way, akin to how we can recall a life-changing moment from years ago but forget what we ate for lunch last week. Currently, even with DeepSeek’s methods, AI tends to forget and remember in a very linear way—recalling whatever was most recent, but not necessarily what was most important, she says.

Despite its attempts to keep a low profile, DeepSeek, based in Hangzhou, China, has built a reputation for pushing the frontier in AI research. The company [shocked the industry at the start of this year](https://www.technologyreview.com/2025/01/24/1110526/china-deepseek-top-ai-despite-sanctions) with the release of DeepSeek-R1, an open-source reasoning model that rivaled leading Western systems in performance despite using far fewer computing resources.
