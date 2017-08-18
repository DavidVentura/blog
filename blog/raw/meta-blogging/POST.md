# Meta
I wanted to write something to keep up with my buzzword-bingo,
so I rewrote my blog using hip technologies.

The idea behind the blog-post flow is to:

* Commit Markdown files to a GitHub repository
* Get GitHub to trigger a build on my Jenkins server
* Sync the resulting built to the web server hosting my blog

The build is triggered when the commit message matches `^deploy [a-zA-Z_.-]`;
on matching commits, Jenkins launches a Docker container that:

* Scans the Markdown for images (both inline and ref)
* Uploads the local images to S3 and replaces the path in the Markdown
* Converts the Markdown to HTML
* Populates a template for the blog-post
* Updates the index file with all posts, sorted by date


![XKCD 917](images/xkcd917.png)

XKCD 917

---------

Everything is on [GitHub](https://github.com/DavidVentura/blogging_like_its_2017)
