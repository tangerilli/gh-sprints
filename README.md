## gh-sprints

#### Initial Setup

1. clone this repo
2. create a `gh-sprints/local_settings.py` file to override values in `gh-sprints/settings.py` like GH token, DB creds, repo name, and org
3. create a venv
4. run `pip install -r requirements.txt`
5. create a DB and add creds to `gh-sprints/local_settings.py`

    **note:**  If you want to use PostgreSQL, the easiest way on OSX is     to download [postgres.app](http://postgresapp.com/), update your    [$PATH](http://postgresapp.com/documentation/cli-tools.html), and
    then open the Postgres cli by typing `psql`.

    Then you can create a   user and database:

    ```
    CREATE USER yourname WITH PASSWORD 'super-strong-password';

    CREATE DATABASE sprints_db;

    GRANT ALL PRIVILEGES ON DATABASE sprints_db to yourname;

    ```

    _additional notes:_

    - your `$USER` is already the `Superuser` for all of `psql`
    - `psql` cheat sheet:

        `\l`    List databases<br>
        `\c <database name>`    Connect to a database<br>
        `\du`       List roles (think "describe users")<br>
        `\dt`       List tables in a connected DB (think "describe tables" ...*don't* think "drop tables" :p )<br>
        `\d <tablename>`    List columns on table<br>
        `\df`       List functions in a connected DB (think "describe functions")


6. initialize the DB by running `python gh-sprints/sprints.py init`
7. populate the DB by running `python gh-sprints/sprints.py snapshot` or click the "Update" button in the UI
8. main it rain PRs :shipit:

#### Deployment

The web app uses Flask, so see their [documentation](http://flask.pocoo.org/docs/0.10/deploying/) for deployment options.

Once the web app is deployed, you probably want to have snapshots happen automatically. The following cron line will do a snapshot once an hour (at the 30 minute mark):

`30 * * * * <path to python> <path to the repo>/sprints.py snapshot 2>&1 | /usr/bin/logger`

You may also want to automatically lock a sprint. The following cron line will lock the current sprint on Friday afternoons:

`0 19 * * 5 <path to python> <path to the repo>/sprints.py lock -s current 2>&1 | /usr/bin/logger`
