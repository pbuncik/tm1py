# -*- coding: utf-8 -*-

import json

from TM1py.Exceptions import TM1pyException
from TM1py.Objects.Dimension import Dimension
from TM1py.Services.HierarchyService import HierarchyService
from TM1py.Services.ObjectService import ObjectService
from TM1py.Services.ProcessService import ProcessService
from TM1py.Services.SubsetService import SubsetService
from TM1py.Utils.Utils import case_and_space_insensitive_equals


class DimensionService(ObjectService):
    """ Service to handle Object Updates for TM1 Dimensions
    
    """

    def __init__(self, rest):
        super().__init__(rest)
        self.hierarchies = HierarchyService(rest)
        self.subsets = SubsetService(rest)

    def create(self, dimension):
        """ Create a dimension

        :param dimension: instance of TM1py.Dimension
        :return: response
        """
        # If Dimension exists. throw Exception
        if self.exists(dimension.name):
            raise Exception("Dimension already exists")
        # If not all subsequent calls successfull -> undo everything that has been done in this function
        try:
            # Create Dimension, Hierarchies, Elements, Edges.
            request = "/api/v1/Dimensions"
            response = self._rest.POST(request, dimension.body)
            for hierarchy in dimension:
                if len(hierarchy.element_attributes) > 0:
                    self.hierarchies.update(hierarchy)
        except TM1pyException as e:
            # undo everything if problem in step 1 or 2
            if self.exists(dimension.name):
                self.delete(dimension.name)
            raise e
        return response

    def get(self, dimension_name):
        """ Get a Dimension

        :param dimension_name:
        :return:
        """
        request = "/api/v1/Dimensions('{}')?$expand=Hierarchies($expand=*)".format(dimension_name)
        response = self._rest.GET(request)
        return Dimension.from_json(response.text)

    def update(self, dimension):
        """ Update an existing dimension

        :param dimension: instance of TM1py.Dimension
        :return: None
        """
        # delete hierarchies that have been removed from the dimension object
        hierarchies_to_be_removed = set(self.hierarchies.get_all_names(dimension.name)) - set(dimension.hierarchy_names)
        for hierarchy_name in hierarchies_to_be_removed:
            self.hierarchies.delete(dimension_name=dimension.name, hierarchy_name=hierarchy_name)

        # update all Hierarchies except for the implicitly maintained 'Leaves' Hierarchy
        for hierarchy in dimension:
            if not case_and_space_insensitive_equals(hierarchy.name, "Leaves"):
                if self.hierarchies.exists(dimension_name=hierarchy.dimension_name, hierarchy_name=hierarchy.name):
                    self.hierarchies.update(hierarchy)
                else:
                    self.hierarchies.create(hierarchy)

    def delete(self, dimension_name):
        """ Delete a dimension

        :param dimension_name: Name of the dimension
        :return:
        """
        request = '/api/v1/Dimensions(\'{}\')'.format(dimension_name)
        return self._rest.DELETE(request)

    def exists(self, dimension_name):
        """ Check if dimension exists
        
        :return: 
        """
        request = "/api/v1/Dimensions('{}')".format(dimension_name)
        return self._exists(request)

    def get_all_names(self):
        """Ask TM1 Server for list with all dimension names

        :Returns:
            List of Strings
        """
        response = self._rest.GET('/api/v1/Dimensions?$select=Name', '')
        dimension_names = list(entry['Name'] for entry in response.json()['value'])
        return dimension_names

    def execute_mdx(self, dimension_name, mdx):
        """ Execute MDX against Dimension. 
        Requires }ElementAttributes_ Cube of the dimension to exist !
 
        :param dimension_name: Name of the Dimension
        :param mdx: valid Dimension-MDX Statement 
        :return: List of Element names
        """
        mdx_skeleton = "SELECT " \
                       "{} ON ROWS, " \
                       "{{ [}}ElementAttributes_{}].DefaultMember }} ON COLUMNS  " \
                       "FROM [}}ElementAttributes_{}]"
        mdx_full = mdx_skeleton.format(mdx, dimension_name, dimension_name)
        request = '/api/v1/ExecuteMDX?$expand=Axes(' \
                  '$filter=Ordinal eq 1;' \
                  '$expand=Tuples($expand=Members($select=Ordinal;$expand=Element($select=Name))))'
        payload = {"MDX": mdx_full}
        response = self._rest.POST(request, json.dumps(payload, ensure_ascii=False))
        raw_dict = response.json()
        return [row_tuple['Members'][0]['Element']['Name'] for row_tuple in raw_dict['Axes'][0]['Tuples']]

    def create_element_attributes_through_ti(self, dimension):
        """ 
        
        :param dimension. Instance of TM1py.Objects.Dimension class
        :return: 
        """
        process_service = ProcessService(self._rest)
        for h in dimension:
            statements = ["AttrInsert('{}', '', '{}', '{}');".format(dimension.name, ea.name, ea.attribute_type[0])
                          for ea
                          in h.element_attributes]
            process_service.execute_ti_code(lines_prolog=statements)
