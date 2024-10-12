import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

# Allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-danceschool',
    version='0.9.3',
    packages=['danceschool'],
    include_package_data=True,
    license='BSD License',
    description='The Django Dance School project:'
    ' a modular, reusable set of designed to integrate'
    ' all of the regular functions of a social dance school'
    ' with the Django CMS content management system',
    long_description=README,
    url='https://github.com/django-danceschool/django-danceschool',
    author='Lee Tucker',
    author_email='lee.c.tucker@gmail.com',
    install_requires=[
        'beautifulsoup4>=4.12.3',
        'Django>=5.0.9,<5.1',
        'django-addanother>=2.2.2',
        'django-admin-list-filter-dropdown>=1.0.3',
        'django-admin-rangefilter>=0.13.2',
        'django-admin-sortable2>=2.2.3',
        'django-allauth>=65.0.2',
        'django-autocomplete-light>=3.11.0',
        'django-braces>=1.16.0',
        'django-ckeditor>=6.7.1',
        'django-ckeditor-filebrowser-filer>=0.5.0',
        'django-cms>=4.1.3',
        'django-colorful>=1.3',
        'django-crispy-forms>=2.3',
        'crispy-bootstrap4>=2024.10',
        'django-dynamic-preferences>=1.16.0',
        'django-easy-pdf>=0.1.1',
        'django-filer>=3.2.3',
        'django-filter>=24.3',
        'django-ical>=1.9.2',
        'django-imagekit>=5.0.0',
        'django-multi-email-field @ git+https://github.com/fle/django-multi-email-field.git@b41318abe81f8a4062136650871135ec49747944',
        'django-multiselectfield>=0.1.13',
        'django-polymorphic>=3.1.0',
        'django-sekizai>=4.1.0',
        'django-utils-six>=2.0',
        'django-weasyprint>=2.3.0',
        'djangocms-4-migration==0.0.2',
        'djangocms-admin-style>=3.3.1',
        'djangocms-alias>=2.0.1',
        'djangocms-attributes-field>=3.0.0',
        'djangocms-frontend>=1.3.4',
        'djangocms_icon>=2.1.0',
        'djangocms-link>=4.0.0',
        'djangocms-picture>=4.1.1',
        'djangocms-text-ckeditor>=5.1.6',
        'djangocms-versioning>=2.0.2',
        'djangorestframework>=3.15.2',
        'djangorestframework-csv>=3.0.2',
        'easy-thumbnails>=2.10',
        'huey>=2.5.2',
        'icalendar>=6.0.0',
        'intervaltree>=3.1.0',
        'jsonschema>=4.23.0',
        'paypalrestsdk>=1.13.3,<2.0',
        'persisting-theory>=1.0',
        'Pillow>=10.4.0',
        'python-dateutil==2.8.2',
        'pytz>=2024.2',
        'qrcode>=8.0',
        'redis>=5.1.1',
        'requests>=2.32.3',
        'six>=1.16.0',
        'squareup>=38.1.0.20240919',
        'stripe>=11.1.0',
        'unicodecsv>=0.14.1',
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content'
    ],
)
