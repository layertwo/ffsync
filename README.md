# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/layertwo/ffsync/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                   |    Stmts |     Miss |   Branch |   BrPart |    Cover |   Missing |
|--------------------------------------- | -------: | -------: | -------: | -------: | -------: | --------: |
| src/\_\_init\_\_.py                    |        0 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/\_\_init\_\_.py         |        2 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/storage\_api.py         |        5 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/token\_api.py           |        5 |        0 |        0 |        0 |     100% |           |
| src/environment/\_\_init\_\_.py        |        0 |        0 |        0 |        0 |     100% |           |
| src/environment/service\_provider.py   |       75 |        0 |        0 |        0 |     100% |           |
| src/routes/\_\_init\_\_.py             |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/bso/\_\_init\_\_.py         |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/bso/delete.py               |       31 |        0 |        0 |        0 |     100% |           |
| src/routes/bso/read.py                 |       36 |        0 |        4 |        0 |     100% |           |
| src/routes/bso/update.py               |       58 |        0 |        8 |        0 |     100% |           |
| src/routes/collections/\_\_init\_\_.py |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/collections/create.py       |       53 |        0 |        6 |        0 |     100% |           |
| src/routes/collections/delete.py       |       28 |        0 |        0 |        0 |     100% |           |
| src/routes/collections/list.py         |       21 |        0 |        0 |        0 |     100% |           |
| src/routes/collections/read.py         |       57 |        0 |       12 |        0 |     100% |           |
| src/routes/collections/update.py       |       48 |        0 |        2 |        0 |     100% |           |
| src/routes/info/\_\_init\_\_.py        |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/info/read\_collections.py   |       22 |        0 |        0 |        0 |     100% |           |
| src/routes/info/read\_counts.py        |       22 |        0 |        0 |        0 |     100% |           |
| src/routes/info/read\_quota.py         |       25 |        0 |        0 |        0 |     100% |           |
| src/routes/info/read\_usage.py         |       22 |        0 |        0 |        0 |     100% |           |
| src/routes/storage/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/storage/delete\_all.py      |       18 |        0 |        0 |        0 |     100% |           |
| src/routes/token/\_\_init\_\_.py       |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/token/request.py            |      113 |        0 |       22 |        0 |     100% |           |
| src/services/api\_router.py            |       15 |        0 |        2 |        0 |     100% |           |
| src/services/oidc\_validator.py        |       88 |        0 |       14 |        0 |     100% |           |
| src/services/storage\_manager.py       |      155 |        0 |       34 |        0 |     100% |           |
| src/services/token\_generator.py       |       29 |        0 |        0 |        0 |     100% |           |
| src/services/user\_manager.py          |       89 |        0 |       26 |        0 |     100% |           |
| src/shared/\_\_init\_\_.py             |        0 |        0 |        0 |        0 |     100% |           |
| src/shared/base\_route.py              |        3 |        0 |        0 |        0 |     100% |           |
| src/shared/exceptions.py               |       87 |        0 |        0 |        0 |     100% |           |
| src/shared/models.py                   |       19 |        0 |        0 |        0 |     100% |           |
| src/shared/oidc.py                     |       10 |        0 |        0 |        0 |     100% |           |
| src/shared/token.py                    |        4 |        0 |        0 |        0 |     100% |           |
| src/shared/user.py                     |       10 |        0 |        0 |        0 |     100% |           |
| src/shared/utils.py                    |       19 |        0 |        2 |        0 |     100% |           |
| **TOTAL**                              | **1169** |    **0** |  **132** |    **0** | **100%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/layertwo/ffsync/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/layertwo/ffsync/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/layertwo/ffsync/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/layertwo/ffsync/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Flayertwo%2Fffsync%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/layertwo/ffsync/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.