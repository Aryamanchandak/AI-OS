manish is looking for maybe a 1 pager, which summaries the ARA (Annual Report Analysis), and refinitiv data for a company. 



he is also looking for a ARA chatbot kind of thing that analyses and summarises the reports from rating agencies, these agencies often downgrade or upgrade bonds, its important to understand the rational behind this upgrade or downgrade.

He also wants a research report generated using AI based on historical financial data for internal use. 

Wants use to speak to Ministry of corporate affairs, for the ROC data to get an update on the changes in the company. a data point that should be considered by use when making the reports and the summary. 
To the above he also wants NCLT data to be used, the legal team has access to the NCLT platform and we will have to speak to them about how we can get access too it. its important so we can quickly check for and sumarrise the companys legal affairs, if a case has been lodged ?? what is the judgement on a case, who is it for and against ?? one thing we want to do here is add some intelligence so we dont overload the team with data. 

all the above things should be in the company one pager ideally. then we can look at NSE/BSE for companies issue summary documents, or terms sheets. this is vital information and allows us to indetail understand what a compnay is issuing and importantly the covenants in this issue, these covenants are incredibly important, we should also look into ways to quantify the covenants and  automate checking them for breaches. Simulate them. should be done manually first then maybe we can automate and simulate it from them. 

Note: It will be hard to scrape data from MCA as a lot of captchas 

for the covenant sections, that covenant extraction and mapping, is important but then we focus on NCD only. look for the word covenants in the header, then use one of the python librariesto read headers, and find the covenants. Pdf libraries which allow this is pdfplumber, pypdf2, camelot. 



then we look into the following Bureau Data, CIBIL data etc. CMIE Subscription, and redd data , that is reference energy disaggregation dataset. 

AI Documentation generation for law purposes, information memorandum and term sheet maybe, where you can prefill things as its will make things soo much easier. 

will it be possible to convert excel formatting and formulas to python. as excel is very brittle, and fails soo often and breaks sooo often, python can make it more robust here.  

AI rating rational changes analysis, trying to understand what triggered these rational changes as in rating agencies rating chenges rational. 

not all companies whose debt we own, are public so we will need to work with capital line to get the private companies data.

universe creation is vvimp 

we look at 4 ratings, CRISIL, ICRA, India Ratings, CARE Ratings. ARA for public companies needs to be quarterly 



every bond has a unique ISIN, which can be used to identify it. G SEC is used as benchmark, dashboard creation is required. can we standardise, the data and the format and then download the excel and financial data, so analysts dont need to go to a different places for the data 


comparative analysis between comapnies, and their debts,

NDA sections restrictions (speak to manish here, not exsactly sure what he wants) 

Company concalls, but from a debt perspective 



rating agencies doc access, understanding the rational behind their decisions. Quantix by crisil is probably the best main data source here, but need to speak to them about API access, they have Data as a service optionality, but no mention of an API. 

other rating agencies, CRISIL, ICRA, India Ratings, Care ask parth how he accesses reports from each. 

one pager based on quarterly financials, should be easy already have a data provider, and pretty high impact imo 

