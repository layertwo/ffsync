# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/layertwo/ffsync/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                   |    Stmts |     Miss |   Branch |   BrPart |    Cover |   Missing |
|--------------------------------------- | -------: | -------: | -------: | -------: | -------: | --------: |
| src/\_\_init\_\_.py                    |        0 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/\_\_init\_\_.py         |        3 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/hawk\_authorizer.py     |       33 |        0 |        2 |        0 |     100% |           |
| src/entrypoint/storage\_api.py         |        5 |        0 |        0 |        0 |     100% |           |
| src/entrypoint/token\_api.py           |        5 |        0 |        0 |        0 |     100% |           |
| src/environment/\_\_init\_\_.py        |        0 |        0 |        0 |        0 |     100% |           |
| src/environment/service\_provider.py   |       97 |        0 |        0 |        0 |     100% |           |
| src/routes/\_\_init\_\_.py             |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/bso/\_\_init\_\_.py         |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/bso/delete.py               |       40 |        0 |        2 |        0 |     100% |           |
| src/routes/bso/read.py                 |       60 |        0 |       14 |        0 |     100% |           |
| src/routes/bso/update.py               |       87 |        0 |       10 |        0 |     100% |           |
| src/routes/collections/\_\_init\_\_.py |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/collections/create.py       |       81 |        0 |       20 |        0 |     100% |           |
| src/routes/collections/delete.py       |       41 |        0 |        4 |        0 |     100% |           |
| src/routes/collections/list.py         |       24 |        0 |        2 |        0 |     100% |           |
| src/routes/collections/read.py         |       83 |        0 |       28 |        0 |     100% |           |
| src/routes/collections/update.py       |       55 |        0 |        4 |        0 |     100% |           |
| src/routes/info/\_\_init\_\_.py        |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/info/read\_collections.py   |       24 |        0 |        2 |        0 |     100% |           |
| src/routes/info/read\_configuration.py |       31 |        0 |        4 |        0 |     100% |           |
| src/routes/info/read\_counts.py        |       24 |        0 |        2 |        0 |     100% |           |
| src/routes/info/read\_quota.py         |       28 |        0 |        2 |        0 |     100% |           |
| src/routes/info/read\_usage.py         |       24 |        0 |        2 |        0 |     100% |           |
| src/routes/storage/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/storage/delete\_all.py      |       23 |        0 |        2 |        0 |     100% |           |
| src/routes/storage/delete\_root.py     |       24 |        0 |        2 |        0 |     100% |           |
| src/routes/token/\_\_init\_\_.py       |        0 |        0 |        0 |        0 |     100% |           |
| src/routes/token/request.py            |      112 |        0 |       22 |        0 |     100% |           |
| src/services/api\_router.py            |       45 |        0 |        2 |        0 |     100% |           |
| src/services/hawk\_service.py          |      106 |        0 |       24 |        0 |     100% |           |
| src/services/oidc\_validator.py        |       90 |        0 |       14 |        0 |     100% |           |
| src/services/storage\_manager.py       |      275 |        0 |       86 |        0 |     100% |           |
| src/services/token\_generator.py       |       19 |        0 |        0 |        0 |     100% |           |
| src/services/user\_manager.py          |       91 |        0 |       26 |        0 |     100% |           |
| src/shared/\_\_init\_\_.py             |        0 |        0 |        0 |        0 |     100% |           |
| src/shared/base\_route.py              |        3 |        0 |        0 |        0 |     100% |           |
| src/shared/exceptions.py               |      166 |        0 |        8 |        0 |     100% |           |
| src/shared/models.py                   |       60 |        0 |       28 |        0 |     100% |           |
| src/shared/oidc.py                     |       10 |        0 |        0 |        0 |     100% |           |
| src/shared/token.py                    |        4 |        0 |        0 |        0 |     100% |           |
| src/shared/user.py                     |       10 |        0 |        0 |        0 |     100% |           |
| src/shared/utils.py                    |       21 |        0 |        2 |        0 |     100% |           |
| **TOTAL**                              | **1804** |    **0** |  **314** |    **0** | **100%** |           |


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