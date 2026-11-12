# World Models

![rw-book-cover](https://www.technologyreview.com/static/media/favicon.1cfcdb44759a0f93ddf5feb5405dd4cc.ico)

## Metadata
- Author: [[Grace Huckins]]
- Full Title: World Models
- Category: #articles
- Summary: AI today is good with digital tasks but struggles with understanding the physical world. Researchers believe teaching AI to build "world models" will help it better predict and act in real environments. These models could improve robots and AI by making them smarter and more reliable in everyday tasks.
- URL: https://www.technologyreview.com/2026/04/21/1135650/world-models-ai-artificial-intelligence/

## Full Document
Today’s AI is still unreliable. Some researchers think solving that problem requires teaching AI systems to understand the world around them.

![](https://wp.technologyreview.com/wp-content/uploads/2026/04/world-models2C.jpg?fit=19998,1958)
Stephanie Arnett/MIT Technology Review | Adobe Stock, Public Domain

AI systems have already gained impressive mastery over the digital world, but the physical world is still humanity’s domain. As it turns out, building an AI system that can compose a novel or code an app is far easier than developing one that can fold laundry or navigate a city street. To get there, many researchers believe, you need something called a world model.

World models are not a new idea, but recent developments from Google DeepMind and Stanford professor Fei-Fei Li’s World Labs, as well as Yann LeCun’s splashy departure from Meta to form a world-model-focused startup, have brought them to the forefront of the AI discussion. OpenAI, too, is getting in on the action by reallocating resources from the shuttered Sora video app to “longer-term world simulation research.” Proponents like Li and LeCun argue that world models will allow researchers to overcome the well-known limitations of LLMs and realize AI’s promise for robotics.

Definitions of the term “world model” vary, but they all center on the ways in which intelligent systems represent the external world. Some scientists would say that humans use our own mental world models to navigate our surroundings and guide our actions; somehow, our brains simulate our environments with enough fidelity to let us effectively predict what we will observe if we push a mug off the edge of a table or tell a friend our honest opinion, and those predictions help us decide what to do.

LLMs might seem to do a good job of this already—they can certainly tell you what will happen if you knock a mug off a table. But research suggests that their “understanding” of the world is brittle. One [study](https://arxiv.org/abs/2406.03689) found that language models trained on a database of simulated New York City taxi trips can provide effective directions for how to navigate from one point in Manhattan to another—unless the model is forced to take occasional detours, in which case it fails completely. This result and others suggest that AI systems with a world model—in this case, an accurate mental map of New York City—could be far more robust and reliable than the flaky LLMs to which we have grown accustomed.

Many researchers think that world models will prove essential to the future of robotics. Li, the World Labs founder, [has written](https://drfeifei.substack.com/p/from-words-to-worlds-spatial-intelligence) about how they could facilitate the development of robots that explore the deep sea and assist health-care providers, but for now, the applications are more modest. The makers of Pokémon Go, for instance, are using billions of images collected by the game’s players to build the first pieces of a world model that, they hope, could [help guide delivery robots](https://www.technologyreview.com/2026/03/10/1134099/how-pokemon-go-is-helping-robots-deliver-pizza-on-time/).

Google DeepMind and World Labs are currently focusing their efforts on building models that can generate interactive, 3D virtual environments from a combination of text, images, and in the case of World Labs, video prompts. Such tools could be used to streamline the design of video games and immersive VR experiences, but compared with large language models, they seem to have a limited range of applications. The real breakthroughs are likely to come from integrating such systems into flexible, intelligent agents that can represent their environments, predict the consequences of their actions, and then decide what to do.
