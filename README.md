
# nyt airflow practice

 A practice project to run airflow locally in Docker, retrieve data from an API, and move to GCS/BQ
 
### what it does

This project represents a simple but fairly common scenario a data person might encounter:

- You need to retrieve data from somewhere, like an API endpoint, at a regular interval and move it to your data warehouse
- This data is either from some in-house source or a niche SaaS app - no perfect solutions for out-of-the-box ETL connectors exist.
- This data source has been active for some period of time, and there is some not insignificant amount of historical data stored in the application or a transactional database, but nobody has bothered to pull the data into the warehouse yet - you need to systematically backfill days/months/years of data.
- You're morally, ethically, and/or philosophically opposed to just throwing it in a cron job and hoping it's someone else's problem by the time it breaks.

### DAGs:

- **get_articles_monthly**
	
	The New York Times generously provides a robust collection of API endpoints that developers can use for non-commercial purposes. One available endpoint is the Archive, which allows a user to request metadata on *all* articles for a given month, and retrieve the articles back in a JSON response.
	
	This DAG runs monthly, on the second day of every month, to retrieve all the available articles for the previous month.
	
	#### Steps: 
	
	1. fetch_articles_to_gcs: this step uses the PythonOperator to run a python function that retrieves one month of article metadata from the API, convert it to JSON Lines format, and move the resultant JSONL object to a GCS bucket.
	2. gcs_to_bq_stage: this step uses the GCStoBigQueryOperator to move the files from the GCS bucket to a staging table.
	3. bq_stage_to_prod: BigQueryInsertJobOperator runs a few DDL statements to a) delete overlapping data from the prod table b) insert the new data c) set an expiration date on the staging table so it doesn't clutter up the stage dataset for all eternity.
	
	#### Airflowy Stuff:
	
	- A YAML file, dag_config.yaml, is used to store variables related to the DAG that are likely to be updated or changed in the future. This prevents any critical configuration options from getting lost in obscurity in the DAG code itself, and makes it easier for future maintainers to keep the DAG functioning as parameters change.
	- Out-of-the-box airflow jinja variables related to DAG run timing are used to dynamically adjust the data retrieved, name files, and name staging tables.
	- Custom jinja variables are used for further templating of the SQL query.
	- Setting a start_date in the past, and setting catchup=True causes Airflow to create DAG runs that occur in the past. These DAG runs populate jinja variables relating to data windows as if they are running in the past. Because the DAG uses these jinja variables to adjust the date window retrieved from the API, this allows for easy, incremental, systematic backfill behavior. 
	- Concurrent DAG runs are set to 1. While the NYT is generous with their data, their generosity has limits, and hitting any API endpoing more than 10 times/minute may get your application blocked. Lowering the concurrency to 1 means that all the backfill tasks to get data from the API will run slowly and sequentially, rather than concurrently.
	- The GCS to BQ operator step takes advantage of BigQuery's ability to natively read and load JSON Lines data. This is *incredibly handy* when it works, because it allows you to take repeated JSON records, such as those returned by an API, and insert them into a table with almost no transformations other than newline delimiting the individual JSON records. BQ's ability to natively handle and query nested/repeated JSON fields is excellent, so you end up with a query-able table that is an extremely faithful representation of the source data. 
	
	HOWEVER, it requires a bit of a leap of faith in the quality and stability of the JSON objects your API returns, because BQ's JSON processing is rigid and doesn't have a lot of flexibility or config options for handling weird/bad JSON data other than skipping records entirely. For example - this API returns a field with the same name, but different capitalization, which BQ doesn't like. There's no way to overcome this errror during the import process. In this case the fields were just duplicates - the data was the same - so I simply deleted one of the fields from the JSON objects before the JSONL data is exported.
	
	A less pleasant, but more error-proof method is to import the JSONL data as CSV (set the delimiter to a rarely used unicode character, like a broken pipe), which gives you a table with each JSONL object as a string, which can then be parsed using bigquery's native JSON functions or any number of other downstream processing options.
 
### on docker
 
 While this project involves running Airflow in Docker, that is just a means to an end to be able to write and test DAGs - this is *not* an exercise in running Airflow in Docker, Docker Administration, Airflow Administration, or anything else like that. The Docker image built is mostly boilerplate from the Airflow production build outside of a few dependencies and options changed, and Airflow's doc is very clear that this is an image only intended for local testing and development. Much more robust customization of the image would be required to even think about running it in any sort of production environment.

## pre-setup

- get an NYT dev account (free): https://developer.nytimes.com/apis
- create a new application in your dev account
- create an api credential and authorize the archive API endpoint
- download docker desktop and follow the guide to make it work: https://www.docker.com/products/docker-desktop/
- have access to a working GCP instance, with the ability to:
	- create a service account that is authorized to make API calls
	- create datasets, create tables, and modify tables in bigquery
	- create files in a GCS bucket

## setup

This all assumes you already have a working instance of Docker Desktop installed, and that you're working on a unix-like system. These steps are more or less an amalgamation of some of the steps outlined in Airflow's own guide on customizing the Airflow-Docker image and running it locally as described in Airflow's own documentation [here](https://airflow.apache.org/docs/apache-airflow/stable/start/docker.html)

Before you begin, you will also need to increase the memory available to Docker if you are still using the default value. Failing to do so won't prevent the docker image from building or initializing, but it will prevent some of the Airflow services from actually running. This can be found in the Settings > Resources in Docker Desktop - set the memory allotted to at least 4gb.

### Step-by-step

 1. Clone the repo locally.
 2. cd to ./Docker and build the custom image:
 
	    docker build . -f Dockerfile --pull --tag nyt-airflow:0.0.1

3. Create plugins/logs directories and Set the Airflow user:

		mkdir -p ./logs ./plugins
		echo -e "AIRFLOW_UID=$(id -u)" > .env
		
4. [Create a GCS Keyfile](https://cloud.google.com/docs/authentication/getting-started) and place it in the gcs_keyfile directory. It should be named **gcs_keyfile.json**. If you don't want to employ the nuclear option and give owner-access to this service account, it will need permissions to do the following:

	- Read and write to a GCS bucket of your choice
	- Create new tables in your stage dataset
	- Write to tables in your prod dataset

5. Initialize the image:

		docker-compose up airflow-init
		
6. Start all services:

		docker-compose up

7. From the docker desktop app, or however you'd prefer to do it, open the airflow webserver. Navigate to admin > connections and create the following connections:

	- **http** type connection called 'nyt_secret', API key goes in the 'password' field. Nothing else needs to be filled out.
	- **google_cloud_platform** type connection called 'google_cloud_default'. The only field that needs to be filled out here is the path to keyfile, and the value will be: '/var/local/gcs_keyfile/gcs_keyfile.json' // todo: add this as env variable in docker-compose.yaml

8. Set your GCP options in **/Docker/dags/get_comments/dag_config.yaml**.

	- gcs_bucket: 

	 - bq_project: 

	- stg_dataset: 

	- prod_dataset:

	- prod_table:
	
	You can also mess with a variety of airflow options here that can change how and when the DAG runs if you'd like, but you probably don't need to, and other configurations are likely to break or get you rate-limited on the API.

9. In the prod_dataset dataset location you specified in the config file, create a prod table using the schema found in the [nyt_articles_schema.json](https://github.com/dana-4mile/nyt-airflow-practice/blob/main/Docker/dags/get_comments/nyt_articles_schema.json "nyt_articles_schema.json") file. There's a variety of ways to do this from python, the console, etc. outlined here: https://cloud.google.com/bigquery/docs/schemas. Partitioning this on Month is probably a good idea too.
 
11. Switch on the DAG and cross your fingers! If all goes well, the DAG will start backfilling data starting in 2010.
