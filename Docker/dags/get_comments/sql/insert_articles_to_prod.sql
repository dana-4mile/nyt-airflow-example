delete from `{{ bq_project }}.{{ prod_dataset }}.{{ prod_table }}`

where pub_date >= (select min(pub_date) from `{{ bq_project }}.{{ stg_dataset }}.{{ data_interval_start.strftime('%Y_%m') }}_articles_stg`)
  and pub_date <= (select max(pub_date) from `{{ bq_project }}.{{ stg_dataset }}.{{ data_interval_start.strftime('%Y_%m') }}_articles_stg`);

insert into `{{ bq_project }}.{{ prod_dataset }}.{{ prod_table }}`

(
  word_count
  ,_id
  ,type_of_material
  ,byline
  ,subsection_name
  ,keywords
  ,section_name
  ,pub_date
  ,lead_paragraph
  ,headline
  ,print_section
  ,snippet
  ,news_desk
  ,multimedia
  ,source
  ,uri
  ,document_type
  ,web_url
  ,print_page
  ,abstract
  ,_bq_insert_date

)

SELECT

word_count
,_id
,type_of_material
,byline
,subsection_name
,keywords
,section_name
,pub_date
,lead_paragraph
,headline
,print_section
,snippet
,news_desk
,multimedia
,source
,uri
,document_type
,web_url
,print_page
,abstract
,current_timestamp() _bq_insert_date

 FROM `{{ bq_project }}.{{ stg_dataset }}.{{ data_interval_start.strftime('%Y_%m') }}_articles_stg`;

 ALTER TABLE `{{ bq_project }}.{{ stg_dataset }}.{{ data_interval_start.strftime('%Y_%m') }}_articles_stg`
 SET OPTIONS (
    expiration_timestamp=date_add(current_timestamp(), interval 7 day)
 )
