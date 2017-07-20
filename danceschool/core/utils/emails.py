from bs4 import BeautifulSoup


def get_text_for_html(html_content):
    '''
    Take the HTML content (from, for example, an email)
    and construct a simple plain text version of that content
    (for example, for inclusion in a multipart email message).
    '''

    soup = BeautifulSoup(html_content)

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()    # rip it out

    # Replace all links with HREF with the link text and the href in brackets
    for a in soup.findAll('a', href=True):
        a.replaceWith('%s <%s>' % (a.string, a.get('href')))

    # get text
    text = soup.get_text()

    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text
