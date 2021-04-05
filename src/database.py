import sqlite3

class Database:
    def __init__(self, filepath):
        self.conn = sqlite3.connect(filepath)

    def __getattr__(self, key):
        return DatabaseTable(self.conn, key)

    def execute(self, statement, values=None):
        with self.conn:
            if values is not None:
                self.conn.execute(statement, values)
            else:
                self.conn.execute(statement)

    def query(self, statement, values=None):
        c = None
        if values is not None:
            c = self.conn.execute(statement, values)
        else:
            c = self.conn.execute(statement)
        return c.fetchall()

class DatabaseTable:
    def __init__(self, conn, table):
        self.conn = conn
        self.table = table
        c = conn.execute("select * from %s" % table)
        self.cols = [row[0] for row in c.description]

    def __getitem__(self, key):
        result = self.conn.execute("select * from %s where %s = ?" % (self.table, self.cols[0]), (key,)).fetchone()
        ret = lambda : None
        if result is None:
            return None
        for index, data in enumerate(result[1:]):
            setattr(ret, self.cols[index + 1], data)
        return ret

    def __setitem__(self, key, value):
        if type(value) is dict:
            value.keys()
            with self.conn:
                statement = "insert or replace into %s (%s) values (%s)" % (
                    self.table,
                    ", ".join((self.cols[0],) + tuple(value.keys())),
                    ", ".join(["?"] * (len(value) + 1)))
                self.conn.execute(statement, (key,) + tuple(value.values()))
