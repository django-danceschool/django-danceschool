from django.template import Template, Context

from easy_pdf.views import PDFTemplateView
import re

from danceschool.core.models import EmailTemplate
from danceschool.core.constants import getConstant


class GiftCertificatePDFView(PDFTemplateView):
    template_name = 'vouchers/pdf/giftcertificate_template.html'

    def get_context_data(self,**kwargs):
        context = super(self.__class__,self).get_context_data(**kwargs)

        template = EmailTemplate.objects.get(id=getConstant('vouchers__giftCertPDFTemplateID'))

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub('\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}','',template.content)

        t = Template(content)

        rendered_content = t.render(Context(context))

        context.update({
            'header': template.subject,
            'content': rendered_content
        })

        return context
