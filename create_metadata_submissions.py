''' 
create core metadata submission tsv 
and reference file csvs (one for data files and one for metadata files):

-----------------------------------------------------
be sure to manually check tsv submission files before actual submission
------------------------------------------------------
'''

import pandas as pd
import yaml
import numpy as np
import re

def add_file_submitter_id(
    df,
    file_name='file_name',
    did='object_id'):
    """Add submitter ID to data frame of files for gen3 submissions"""

    submitter_ids = (df[file_name].str.rsplit('.', 1).str[0] +
                          '_' + df[did].str[-4:])
    df.insert(0,'submitter_id',submitter_ids)

#read in file dataframe created from the upload_data.py file
config = yaml.safe_load(open('config.yaml','r'))

#replace_space_with_percent = lambda s:s.file_name.str.replace(" ","%",regex=False)
files_df = (
    pd.read_csv(config['csv_file_save_path'])
    # .assign(
    #     file_name=lambda s: replace_space_with_percent(s) 
    #)
)
#add metadata from file names
contains = files_df.file_name.str.contains
#spatial types
is_state = contains("_S|state")
is_county = contains("_C|counties")
is_zip = contains("_Z|zcta")
is_tract = contains("_T|tract")
is_location = contains("us-wide-moudsCleaned")
spatial_cond_list = [is_state,is_county,is_zip,is_tract,is_location]
spatial_choice_list = ['State','County','Zip','Tract','Location']
files_df['file_spatial_type'] = np.select(spatial_cond_list,spatial_choice_list,None)
#data types
is_gpkg = contains("\.gpkg$")
is_csv = contains("\.csv$")
is_md = contains("\.md$")
is_geographic = contains("dbf$|prj$|shp$|shx$")
is_crosswalk = contains('COUNTY_ZIP|TRACT_ZIP|ZIP_COUNTY|ZIP_TRACT')
is_xlsx = contains('.xlsx$')
data_type_cond_list = [is_gpkg,is_csv,is_md,is_geographic,is_crosswalk]
data_type_choice_list = ['gpkg','Geographic Data','Documentation','Geographic Boundaries','Geographic Crosswalk']

files_df['file_data_type'] = np.select(data_type_cond_list,data_type_choice_list,None)

data_format_cond_list = [is_gpkg,is_csv,is_md,is_geographic,is_xlsx]
data_format_choice_list = ['GPKG','CSV','MD','SHAPEFILE','XLSX']
files_df['file_data_format'] = np.select(data_format_cond_list,data_format_choice_list)

#TODO: variable names and descriptions
#upload metadata
tbl = []
themes = []
with open(config['constructs_md'],'r',encoding='utf-8') as f:
    for line in f:
        if re.search("^###",line):
            theme = re.sub("^### |\n","",line)
        
        if re.search(".*\|.*\|.*",line) \
            and not re.search("Variable Construct",line) \
            and not re.search(":-----",line):
            row = line.split("|")
            tbl.append(row)
            #for each table line, get the variable construct
            #delete unnessary text in variable
            themes.append(re.sub("^ | $|Variables","",theme))

metadata_df = pd.DataFrame(tbl).loc[:,1:5]

metadata_df.columns = [
    'Variable Construct',
    'Variable Proxy',
    'Source',
    'Metadata',
    'Spatial Scale'
]
metadata_df['Themes'] = themes

metadata_df['Spatial Scale'].\
    replace(" ","",regex=True,inplace=True)

def copy_metadata_for_spatial_scales(series):
    ''' 
    create record of metadata for each spatial scale
    ''' 
    series_list = [
        series.replace({series['Spatial Scale']:x}) 
        for x in series['Spatial Scale'].split(",")
    ]
    return pd.DataFrame(series_list)

metadata_expanded_df = pd.concat(
    [
        copy_metadata_for_spatial_scales(df)
        for i,df in metadata_df.iterrows()
    ]
)
metadata_expanded_df.reset_index(drop=True,inplace=True)
#some variable constructs have same name so just use unique ids
metadata_expanded_df['id'] = (
    metadata_expanded_df['Themes']
    .str.lower()
    .str.replace(" ","") + 
    '_' +
    metadata_expanded_df['Spatial Scale'].str.lower() +
    metadata_expanded_df.index.astype(str) 
)
# for data files -- get file prefixes to join with data file dataframe
metadata_expanded_df['metadata_for_data'] = (
    metadata_expanded_df.Metadata
    .str.replace(" ","")
    .str.extract('([A-Za-z]+\d\d|GeographicBoundaries|CrosswalkFiles)')[0]
    .str.replace("GeographicBoundaries","geographic") #geographic
    .str.replace("CrosswalkFiles","crosswalk") #crosswalk 
)
#for markdown metadata files -- join on file name
metadata_expanded_df['metadata_for_markdown'] = (
    metadata_expanded_df['Metadata']
    .str.replace(".*/metadata/|\)| ","")
    .str.replace("\%20"," ") #replace markdown url space placeholders with a space
    #.values
)

# get file metadata names from file names
data_file_df = files_df.loc[files_df['file_data_format'].str.contains("CSV|SHAPEFILE")]
data_file_df['metadata_variable_constructs']  = ( 
    data_file_df
    .file_name
    .str.replace("_.*\..*","")
)
#geographic and crosswalk are gleaned from data types and not file names
is_geo = data_file_df.file_data_type=='Geographic Boundaries'
is_crosswalk = data_file_df.file_data_type=='Geographic Crosswalk'
data_file_df.loc[is_geo,'metadata_variable_constructs'] = 'geographic'
data_file_df.loc[is_crosswalk,'metadata_variable_constructs'] = 'crosswalk'


#make tsv files for submission
#reference file: get file name, spatial, and type of file
#core_metadata_collection : 
# ## core_metadata_collection.submitter_id, Variable Construct, Variable Proxy, Source, metadata_file
## TODO: get data limitations, data source, etc from extracted
core_metadata_collection_mappings = {
    'id':'submitter_id',
    'Variable Construct':'title', 
    'Variable Proxy':'description',
    'Source':'source', 
    'Metadata':'relation',
    'Themes':'subject',
    'Spatial Scale':'data_type' # using data_type as its already ETL'ed. TODO: ETL the coverage property
}
reference_file_mappings = {
    'id':'core_metadata_collections.submitter_id',
    'file_spatial_type':'data_category',
    'file_data_type':'data_type',
    'file_data_format':'data_format',
    'gen3_object_id':'object_id'
}
reference_file_fields = [
    'data_category',
    'md5sum',
    'file_size',
    'file_name',	
    'core_metadata_collections.submitter_id',
    'data_format',	
    'data_type',
    'object_id',
    'type'
]
core_metadata_collection = (
    metadata_expanded_df
    [core_metadata_collection_mappings.keys()]
    .rename(columns=core_metadata_collection_mappings)
)
# Node name
core_metadata_collection['type'] = 'core_metadata_collection'
# Add creator property
core_metadata_collection['creator'] = 'Center for Spatial Data Science (CSDS) at the University of Chicago'
# link to project
core_metadata_collection['projects.code'] = 'OEPS'

#join files with metadata -- 
# note one data file can be in multiple variable constructs
reference_data_df = (
    data_file_df
    .merge(
        metadata_expanded_df,
        how='left',
        left_on=['metadata_variable_constructs','file_spatial_type'],
        right_on=['metadata_for_data','Spatial Scale']
    )
    .rename(columns=reference_file_mappings)
    .assign(
        type='reference_file',
    )
    [reference_file_fields] 
)

#multiple links are specified with comma separated list 
#originally thought individual records represented one link so added this
#https://gen3.org/resources/user/submit-data/#specifying-multiple-links

reference_data_df['core_metadata_collections.submitter_id'] = (
    reference_data_df
    .fillna('None')
    .groupby(['file_size','file_name','md5sum','object_id'])
    ['core_metadata_collections.submitter_id']
    .transform(lambda x:','.join(x))
)
reference_data_df.drop_duplicates(inplace=True)
#join metadata df with files to get only referenced metadata 
# note one markdown file can be involved in multiple variable constructs
reference_md_df = (
    metadata_expanded_df
    .merge(
        files_df,
        how='left',
        right_on=['file_name'],
        left_on=['metadata_for_markdown']
    )
    .assign(
        file_data_type = 'markdown',
        file_spatial_type='Documentation',
        data_category='Documentation',
        type='reference_file'
    )
    .rename(columns=reference_file_mappings)
    [reference_file_fields]
)
#multiple links are specified with comma separated list 
#originally thought individual records represented one link so added this
#https://gen3.org/resources/user/submit-data/#specifying-multiple-links
reference_md_df['core_metadata_collections.submitter_id'] = (
    reference_md_df
    .fillna('None')
    .groupby(['file_size','file_name','md5sum','object_id'])
    ['core_metadata_collections.submitter_id']
    .transform(lambda x:','.join(x))
)
reference_md_df.drop_duplicates(inplace=True)

#add submitter ids 
add_file_submitter_id(reference_md_df)
add_file_submitter_id(reference_data_df)

reference_data_df.to_csv("metadata/reference_data_all_df.tsv",sep='\t',index=False)
reference_md_df.to_csv("metadata/reference_md_df.tsv",sep='\t',index=False)
core_metadata_collection.to_csv("metadata/core_metadata_collection.tsv",sep='\t',index=False)

