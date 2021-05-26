The idea of this repository is to explore and combine multiple technologies to achieve a static blog.

* Commit Markdown files to a github repository
* Jenkins should trigger and run the 'build' step
  * Set up required environment in a Docker container
  * Convert HTML to Markdown, upload images to S3 and use them as source.
  * Upload newly built HTML files to webserver
* Push a notification of successful deployment somewhere


The result is [this](https://blog.davidv.dev/).
