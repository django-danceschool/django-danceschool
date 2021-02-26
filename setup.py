import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

# Allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-danceschool',
    version='0.9.1',
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
        'beautifulsoup4>=4.6.0',
        'Django>=3.1.6,<3.2',
        'django-admin-rangefilter>=0.6.4',
        'django-admin-sortable2>=0.7.2',
        'django-allauth>=0.31.0',
        'django-autocomplete-light>=3.8.1',
        'django-braces>=1.8.1',
        'django-ckeditor>=5.4.0',
        'django-ckeditor-filebrowser-filer>=0.3.0',
        'django-cms>=3.8.0',
        'django-colorful>=1.2',
        'django-crispy-forms>=1.6.0',
        'django-dynamic-preferences>=1.8.1',
        'django-easy-pdf>=0.1.1',
        'django-filer>=1.7.0',
        'django-ical>=1.4',
        'django-imagekit>=3.3',
        'django-multiselectfield>=0.1.5',
        'django-polymorphic>=3.0.0',
        'django-sekizai>=0.10.0',
        'django-utils-six>=2.0',
        'djangocms-admin-style>=1.2.6.2',
        'djangocms-bootstrap4>=1.3.1',
        'djangocms-icon>=1.3.0',
        'djangocms-link>=2.3.1',
        'djangocms-picture>=2.1.3',
        'djangocms-text-ckeditor>=3.7.0',
        'easy-thumbnails>=2.3',
        'huey>=2.3.0',
        'icalendar>=3.9.0',
        'intervaltree>=2.1.0',
        'paypalrestsdk>=1.12.0',
        'persisting-theory>=0.2.1',
        'Pillow>=3.4.2',
        'python-dateutil>=2.4.1',
        'pytz>=2017.2',
        'redis>=3.1.0',
        'requests>=2.6.0',
        'six>=1.10.0',
        'squareconnect>=2.20180712.3',
        'stripe>=1.62.0',
        'unicodecsv>=0.14.1',
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content'
    ],
)
