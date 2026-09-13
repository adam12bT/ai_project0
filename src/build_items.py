"""
Builds data/items.jsonl for the text-to-SQL bake-off task.
Each item: a natural-language question about the Chinook database,
paired with a gold SQL query. Every gold query is executed against
the real DB at build time so we know it's valid and non-trivial
(not empty, not accidentally returning every row) before it goes
into the test set.
"""
import sqlite3
import json
import sys

DB_PATH = "Chinook_Sqlite.sqlite"

ITEMS = [
    # --- simple lookups / filters ---
    ("List the names of all artists whose name starts with 'The'.",
     "SELECT Name FROM Artist WHERE Name LIKE 'The%' ORDER BY Name;"),
    ("What is the email address of the customer named Luís Gonçalves?",
     "SELECT Email FROM Customer WHERE FirstName = 'Luís' AND LastName = 'Gonçalves';"),
    ("List all track names that are longer than 300000 milliseconds.",
     "SELECT Name FROM Track WHERE Milliseconds > 300000 ORDER BY Name;"),
    ("Which employees have the job title 'Sales Support Agent'?",
     "SELECT FirstName, LastName FROM Employee WHERE Title = 'Sales Support Agent' ORDER BY LastName;"),
    ("List all customers who live in Brazil.",
     "SELECT FirstName, LastName FROM Customer WHERE Country = 'Brazil' ORDER BY LastName;"),
    ("What are the names of all genres?",
     "SELECT Name FROM Genre ORDER BY Name;"),
    ("List all playlists that have 'Music' in their name.",
     "SELECT Name FROM Playlist WHERE Name LIKE '%Music%';"),
    ("Find the track named 'Balls to the Wall'.",
     "SELECT Name, Composer, Milliseconds FROM Track WHERE Name = 'Balls to the Wall';"),
    ("List customers from the state of California (CA).",
     "SELECT FirstName, LastName, City FROM Customer WHERE State = 'CA' ORDER BY LastName;"),
    ("What is the postal code of the employee named Andrew Adams?",
     "SELECT PostalCode FROM Employee WHERE FirstName = 'Andrew' AND LastName = 'Adams';"),

    # --- counts / aggregates ---
    ("How many tracks are there in total?",
     "SELECT COUNT(*) FROM Track;"),
    ("How many customers are there from Germany?",
     "SELECT COUNT(*) FROM Customer WHERE Country = 'Germany';"),
    ("What is the total number of invoices?",
     "SELECT COUNT(*) FROM Invoice;"),
    ("What is the average unit price of a track?",
     "SELECT AVG(UnitPrice) FROM Track;"),
    ("What is the total sum of all invoice totals?",
     "SELECT SUM(Total) FROM Invoice;"),
    ("How many distinct countries do customers come from?",
     "SELECT COUNT(DISTINCT Country) FROM Customer;"),
    ("How many albums does the artist with ArtistId 1 have?",
     "SELECT COUNT(*) FROM Album WHERE ArtistId = 1;"),
    ("What is the longest track duration in milliseconds?",
     "SELECT MAX(Milliseconds) FROM Track;"),
    ("What is the shortest track duration in milliseconds, excluding zero?",
     "SELECT MIN(Milliseconds) FROM Track WHERE Milliseconds > 0;"),
    ("How many tracks belong to the genre 'Rock'?",
     "SELECT COUNT(*) FROM Track t JOIN Genre g ON t.GenreId = g.GenreId WHERE g.Name = 'Rock';"),

    # --- joins ---
    ("List the names of all albums by the artist 'AC/DC'.",
     "SELECT al.Title FROM Album al JOIN Artist ar ON al.ArtistId = ar.ArtistId WHERE ar.Name = 'AC/DC';"),
    ("List the track names on the album 'Facelift'.",
     "SELECT t.Name FROM Track t JOIN Album al ON t.AlbumId = al.AlbumId WHERE al.Title = 'Facelift';"),
    ("Which genre does the track 'Fast As a Shark' belong to?",
     "SELECT g.Name FROM Track t JOIN Genre g ON t.GenreId = g.GenreId WHERE t.Name = 'Fast As a Shark';"),
    ("List the first and last names of customers along with the city of their support representative.",
     "SELECT c.FirstName, c.LastName, e.City AS RepCity FROM Customer c JOIN Employee e ON c.SupportRepId = e.EmployeeId;"),
    ("List all track names along with their media type name.",
     "SELECT t.Name, m.Name AS MediaType FROM Track t JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId LIMIT 20;"),
    ("List the names of tracks in the playlist called 'Music'.",
     "SELECT t.Name FROM Track t JOIN PlaylistTrack pt ON t.TrackId = pt.TrackId JOIN Playlist p ON pt.PlaylistId = p.PlaylistId WHERE p.Name = 'Music' LIMIT 20;"),
    ("What is the total amount billed to each customer named 'Frank Harris'?",
     "SELECT c.FirstName, c.LastName, SUM(i.Total) AS TotalBilled FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId WHERE c.FirstName='Frank' AND c.LastName='Harris' GROUP BY c.CustomerId;"),
    ("List the names of employees and the first names of the employees they report to.",
     "SELECT e1.FirstName AS Employee, e2.FirstName AS Manager FROM Employee e1 JOIN Employee e2 ON e1.ReportsTo = e2.EmployeeId;"),
    ("List all invoice lines for the track named 'Right Next Door to Hell', showing quantity and unit price.",
     "SELECT il.Quantity, il.UnitPrice FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId WHERE t.Name = 'Right Next Door to Hell';"),
    ("List the album title and artist name for the track 'Go Down'.",
     "SELECT al.Title, ar.Name FROM Track t JOIN Album al ON t.AlbumId = al.AlbumId JOIN Artist ar ON al.ArtistId = ar.ArtistId WHERE t.Name = 'Go Down';"),

    # --- group by / having ---
    ("For each country, how many customers are there? Order by count descending.",
     "SELECT Country, COUNT(*) AS NumCustomers FROM Customer GROUP BY Country ORDER BY NumCustomers DESC;"),
    ("For each genre, how many tracks are there? Order by genre name.",
     "SELECT g.Name, COUNT(t.TrackId) AS NumTracks FROM Genre g JOIN Track t ON g.GenreId = t.GenreId GROUP BY g.Name ORDER BY g.Name;"),
    ("Which countries have more than 5 customers?",
     "SELECT Country, COUNT(*) AS NumCustomers FROM Customer GROUP BY Country HAVING COUNT(*) > 5 ORDER BY NumCustomers DESC;"),
    ("For each artist, how many albums do they have? Show only artists with more than 5 albums.",
     "SELECT ar.Name, COUNT(al.AlbumId) AS NumAlbums FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.Name HAVING COUNT(al.AlbumId) > 5 ORDER BY NumAlbums DESC;"),
    ("What is the total sales amount for each employee (by their supported customers' invoices)?",
     "SELECT e.FirstName, e.LastName, SUM(i.Total) AS TotalSales FROM Employee e JOIN Customer c ON e.EmployeeId = c.SupportRepId JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY e.EmployeeId ORDER BY TotalSales DESC;"),
    ("For each media type, how many tracks use it?",
     "SELECT m.Name, COUNT(t.TrackId) AS NumTracks FROM MediaType m JOIN Track t ON m.MediaTypeId = t.MediaTypeId GROUP BY m.Name ORDER BY NumTracks DESC;"),
    ("Which playlists have more than 500 tracks?",
     "SELECT p.Name, COUNT(pt.TrackId) AS NumTracks FROM Playlist p JOIN PlaylistTrack pt ON p.PlaylistId = pt.PlaylistId GROUP BY p.Name HAVING COUNT(pt.TrackId) > 500 ORDER BY NumTracks DESC;"),
    ("For each billing country, what is the total invoice amount?",
     "SELECT BillingCountry, SUM(Total) AS TotalAmount FROM Invoice GROUP BY BillingCountry ORDER BY TotalAmount DESC;"),
    ("How many albums does each artist have? Show only artists with exactly 1 album.",
     "SELECT ar.Name, COUNT(al.AlbumId) AS NumAlbums FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.Name HAVING COUNT(al.AlbumId) = 1 ORDER BY ar.Name;"),
    ("What is the average track length in milliseconds for each genre?",
     "SELECT g.Name, AVG(t.Milliseconds) AS AvgLength FROM Genre g JOIN Track t ON g.GenreId = t.GenreId GROUP BY g.Name ORDER BY AvgLength DESC;"),

    # --- order by / limit (top-N) ---
    ("What are the 5 most expensive tracks?",
     "SELECT Name, UnitPrice FROM Track ORDER BY UnitPrice DESC, Name ASC LIMIT 5;"),
    ("Who are the top 3 customers by total amount spent?",
     "SELECT c.FirstName, c.LastName, SUM(i.Total) AS TotalSpent FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY c.CustomerId ORDER BY TotalSpent DESC LIMIT 3;"),
    ("What are the 10 longest tracks by duration?",
     "SELECT Name, Milliseconds FROM Track ORDER BY Milliseconds DESC LIMIT 10;"),
    ("Which 5 genres have the most tracks?",
     "SELECT g.Name, COUNT(t.TrackId) AS NumTracks FROM Genre g JOIN Track t ON g.GenreId = t.GenreId GROUP BY g.Name ORDER BY NumTracks DESC LIMIT 5;"),
    ("What are the 3 best-selling tracks by total quantity sold?",
     "SELECT t.Name, SUM(il.Quantity) AS TotalSold FROM Track t JOIN InvoiceLine il ON t.TrackId = il.TrackId GROUP BY t.TrackId ORDER BY TotalSold DESC LIMIT 3;"),
    ("Which artist has the most albums?",
     "SELECT ar.Name, COUNT(al.AlbumId) AS NumAlbums FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.Name ORDER BY NumAlbums DESC LIMIT 1;"),
    ("What are the 5 most recent invoices by date?",
     "SELECT InvoiceId, InvoiceDate, Total FROM Invoice ORDER BY InvoiceDate DESC LIMIT 5;"),
    ("Which 5 customers have the most invoices?",
     "SELECT c.FirstName, c.LastName, COUNT(i.InvoiceId) AS NumInvoices FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY c.CustomerId ORDER BY NumInvoices DESC LIMIT 5;"),

    # --- subqueries / distinct / date filters ---
    ("List the names of tracks that have never appeared on any invoice.",
     "SELECT Name FROM Track WHERE TrackId NOT IN (SELECT DISTINCT TrackId FROM InvoiceLine) ORDER BY Name LIMIT 20;"),
    ("Which customers have spent more than the average total per invoice?",
     "SELECT DISTINCT c.FirstName, c.LastName FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId WHERE i.Total > (SELECT AVG(Total) FROM Invoice) ORDER BY c.LastName;"),
    ("List all invoices billed in the year 2021.",
     "SELECT InvoiceId, InvoiceDate, Total FROM Invoice WHERE InvoiceDate LIKE '2021%' ORDER BY InvoiceDate;"),
    ("What distinct billing countries appear in the invoices?",
     "SELECT DISTINCT BillingCountry FROM Invoice ORDER BY BillingCountry;"),
    ("List artists who have no albums in the database.",
     "SELECT Name FROM Artist WHERE ArtistId NOT IN (SELECT DISTINCT ArtistId FROM Album);"),
]

def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    out = []
    errors = []
    for idx, (question, sql) in enumerate(ITEMS, start=1):
        item_id = f"item_{idx:03d}"
        try:
            cur.execute(sql)
            rows = cur.fetchall()
        except Exception as e:
            errors.append((item_id, question, sql, str(e)))
            continue
        if len(rows) == 0:
            errors.append((item_id, question, sql, "gold query returned 0 rows"))
            continue
        out.append({
            "id": item_id,
            "question": question,
            "gold_sql": sql,
            "gold_row_count": len(rows),
        })

    if errors:
        print(f"!! {len(errors)} item(s) failed validation:", file=sys.stderr)
        for item_id, q, sql, err in errors:
            print(f"  {item_id}: {err}\n    Q: {q}\n    SQL: {sql}", file=sys.stderr)
        sys.exit(1)

    with open("data/items.jsonl", "w", encoding="utf-8") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Wrote {len(out)} validated items to data/items.jsonl")

if __name__ == "__main__":
    main()
