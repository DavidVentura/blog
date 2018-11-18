I do not like reddit's new UI - I liked the old and compact one a lot more; see the image for comparison
![reddit](images/reddit-old-new.png)

I kept getting annoyed by Firefox' autocomplete leading me to the 'www.reddit.com' instead of 'old.reddit.com' and I decided to modify my browsing history.  
A quick search online pointed me to [the docs for "The Places" database](https://developer.mozilla.org/en-US/docs/Mozilla/Tech/Places/Database); which shows that you can simply edit a table in an sqlite db to modify your history

Running 
```
$ sqlite3 ~/.mozilla/firefox/*.default/places.sqlite
> update moz_places set url = replace(url, '//reddit', '//old.reddit') where url like '%//reddit%';
> update moz_places set url = replace(url, 'www.reddit', 'old.reddit') where url like '%www.reddit%';
> exit
```

ensures I don't get redirected to the new UI anymore.
