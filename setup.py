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
        'beautifulsoup4>=4.11.1',
        'Django>=3.2.16,<4.0',
        'django-addanother>=2.2.2',
        'django-admin-list-filter-dropdown>=1.0.3',
        'django-admin-rangefilter>=0.9.0',
        'django-admin-sortable2>=1.0.4',
        'django-allauth>=0.51.0',
        'django-autocomplete-light>=3.9.5rc1',
        'django-braces>=1.15.0',
        'django-ckeditor>=6.3.2',
        'django-ckeditor-filebrowser-filer>=0.3.0',
        'django-cms>=3.11.0',
        'django-colorful>=1.3',
        'django-crispy-forms>=1.6.0',
        'django-dynamic-preferences>=1.8.1',
        'django-easy-pdf>=0.1.1',
        'django-filer>=1.7.0',
        'django-filter>=22.1',
        'django-ical>=1.8.3',
        'django-imagekit>=4.1.0',
        'django-multi-email-field>=0.6.2',
        'django-multiselectfield>=0.1.12',
        'django-polymorphic>=3.1.0',
        'django-sekizai>=3.0.1',
        'django-utils-six>=2.0',
        'djangocms-admin-style>=3.2.0',
        'djangocms_bootstrap4>=3.0.0',
        'djangocms_icon>=2.0.0',
        'djangocms-link>=3.1.0',
        'djangocms-picture>=4.0.0',
        'djangocms-text-ckeditor>=5.1.1',
        'djangorestframework>=3.14.0',
        'djangorestframework-csv>=2.1.1',
        'easy-thumbnails>=2.8.3',
        'huey>=2.4.4',
        'icalendar>=5.0.1',
        'intervaltree>=3.1.0',
        'paypalrestsdk>=1.13.1',
        'persisting-theory>=1.0',
        'Pillow>=9.3.0',
        'python-dateutil>=2.8.2',
        'pytz>=2022.6',
        'qrcode>=7.3.1',
        'redis>=4.3.4',
        'requests>=2.28.1',
        'six>=1.16.0',
        'squareup>=23.0.0.20221019',
        'stripe>=4.2.0',
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
