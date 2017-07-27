# Import packages
from pyomo.environ import *
import pandas as pd
import numpy as np
import pickle
from pyomo.opt import SolverResults
import time
import os
from pyomo.opt import SolverStatus, TerminationCondition



class SimpleCGE:
    """Pyomo port of splcge.gams from GAMS model library"""
    """Inputs: dat, solver """


    def __init__(self):

        self.model_abstract()


    def model_abstract(self):
        
        self.m = AbstractModel()

        # ----------------------------------------------- #
        #DEFINE SETS

        self.m.i = Set(doc='goods')
        self.m.h = Set(doc='factor')
        self.m.u = Set(doc='SAM entry')
        
        # ----------------------------------------------- #
        #DEFINE PARAMETERS
        
        self.m.sam = Param(self.m.u, self.m.u, 
                           doc='social accounting matrix',
                           mutable = True)


        def X0_init(model, i):
            return model.sam[i, 'HOH']

        self.m.X0 = Param(self.m.i,
                          initialize=X0_init,
                          doc='hh consumption of i-th good',
                          mutable = True)

        def F0_init(model, h, i):
            return model.sam[h, i]

        self.m.F0 = Param(self.m.h, self.m.i,
                          initialize=F0_init,
                          doc='h-th factor input by j-th firm',
                          mutable=True)

        def Z0_init(model, i):
            return sum(model.F0[h, i] for h in model.h)

        self.m.Z0 = Param(self.m.i,
                          initialize=Z0_init,
                          doc='output of j-th good',
                          mutable = True)
        
        def FF_init(model, h):
            return model.sam['HOH', h]
        
        self.m.FF = Param(self.m.h,
                          initialize=FF_init,
                          doc = 'factor endowment of the h-th factor',
                          mutable = True)
        
        # --------------------------------------------- #
        # CALIBRATION
        
        def alpha_init(model, i):
            return model.X0[i] / sum(model.X0[j] for j in model.i) 
        
        self.m.alpha = Param(self.m.i,
                             initialize=alpha_init,
                             doc='share parameter in utility function',
                             mutable = True)
        
        def beta_init(model, h, i):
            return model.F0[h, i] / sum(model.F0[k, i] for k in model.h)

        self.m.beta = Param(self.m.h, self.m.i,
                            initialize=beta_init,
                            doc='share parameter in production function',
                            mutable = True)
        
        def b_init(model, i):
            return model.Z0[i] / np.prod([model.F0[h, i]**model.beta[h, i] for h in model.h])

        self.m.b = Param(self.m.i,
                         initialize=b_init,
                         doc='scale parameter in production function',
                         mutable = True)
        
        # -----------------------------------------------------#
        #Define model system
        #DEFINE VARIABLES
        
        self.m.X = Var(self.m.i,
                       initialize=X0_init,
                       within=PositiveReals,
                       doc='household consumption of the i-th good')
        
        self.m.F = Var(self.m.h, self.m.i,
                       initialize=F0_init,
                       within=PositiveReals,
                       doc='the h-th factor input by the j-th firm')
        
        self.m.Z = Var(self.m.i,
                       initialize=Z0_init,
                       within=PositiveReals,
                       doc='output of the j-th good')
        
        def p_init(model, v):
            return 1
        
        self.m.px = Var(self.m.i,
                        initialize=p_init,
                        within=PositiveReals,
                        doc='demand price of the i-th good')
        
        self.m.pz = Var(self.m.i,
                        initialize=p_init,
                        within=PositiveReals,
                        doc='supply price of the i-th good')

        
        self.m.pf = Var(self.m.h,
                        initialize=p_init,
                        within=PositiveReals,
                        doc='the h-th factor price')
        
        # ------------------------------------------------------ #
        # DEFINE EQUATIONS
        # define constraints
        
        def eqX_rule(model, i):
            return (model.X[i] == model.alpha[i] * sum(model.pf[h] * model.FF[h] / model.px[i] for h in model.h))
        
        self.m.eqX = Constraint(self.m.i,
                                rule=eqX_rule,
                                doc='household demand function')
        
        
        def eqpz_rule(model, i):
            return (model.Z[i] == model.b[i] * np.prod([model.F[h, i]**model.beta[h, i] for h in model.h]))
 
    
        self.m.eqpz = Constraint(self.m.i,
                                 rule=eqpz_rule,
                                 doc='production function')
       

        def eqF_rule(model, h, i):
            return (model.F[h, i] == model.beta[h, i] * model.pz[i] * model.Z[i] / model.pf[h])

        self.m.eqF = Constraint(self.m.h, self.m.i,
                                rule=eqF_rule,
                                doc='factor demand function')


        def eqpx_rule(model, i):
            return (model.X[i] == model.Z[i])

        self.m.eqpx = Constraint(self.m.i,
                                 rule=eqpx_rule,
                                 doc='good market clearning condition')


        def eqpf_rule(model, h):
            return (sum(model.F[h, j] for j in model.i) == model.FF[h])

        self.m.eqpf = Constraint(self.m.h,
                                 rule=eqpf_rule,
                                 doc='factor market clearning condition')


        def eqZ_rule(model, i):
            return (model.px[i] == model.pz[i])

        self.m.eqZ = Constraint(self.m.i,
                                rule=eqZ_rule,
                                doc='price equation')
        
        # ------------------------------------------------------- #
        # DEFINE OBJECTIVE


        def obj_rule(model):
            return np.prod([model.X[i]**model.alpha[i] for i in model.i])

        self.m.obj = Objective(rule=obj_rule,
                               sense=maximize,
                               doc='utility function [fictitious]')
        
        # ------------------------------------------------------- #
        # CREATE MODEL INSTANCE
        
        

        # TODO:
        # separate each of these steps into functions,
        # can then import function defs
        # def model_sets, def model_params, def model_contraints, def model_objective...
        # also: model_calibrate, model_sim, model_shock, ...

    def model_data(self, data_dir = ''):
        
        if not data_dir.endswith("/") and data_dir != "":
            data_dir = data_dir + "/"
        
        if (data_dir == ""):
            print("Please specify where you would like to load data from")
        

        
        elif not os.path.exists(data_dir):
            print("please enter a valid data directory")
        
        else:
        
            data = DataPortal()
            
            for filenames in os.listdir(data_dir):
                if filenames.startswith("set"):                
    
                    dat_type,names,file_type = filenames.split('-')
                    data.load(filename = data_dir + filenames, format = 'set', set = names)                
                    print("File '" + filenames + "' was loaded into set: " + names)
                    
                elif filenames.startswith("param"):
                    
                    dat_type,names,file_type = filenames.split('-')
                    print("File '" + filenames + "' was loaded into param: " + names)             
    
                    data.load(filename = data_dir + filenames, param = names, format='array')
                
                else:
                    print(filenames, " is not in the right format and was not loaded into DataPortal")
                    
            self.data = data


    def model_instance(self):
        
        try:
        
            self.base = self.m.create_instance(self.data)
            self.base.pf['LAB'].fixed = True
            
            print("BASE instance created. Call `model_postprocess` to output or `model_calibrate` to solve.")
        
        except:
            print("Unable to create BASE instance. Please make sure data is loaded")
              

    def model_sim (self):
        
        try:
            
            if self.base:
        
                self.sim = self.m.create_instance(self.data)
                self.sim.pf['LAB'].fixed = True
                
                print("SIM instance created. Note, this is currently the same as BASE. Call `model_modify_instance` to modify.")
        
        except AttributeError:
            print("You must create BASE instance first.")
        
    
    def model_modify_instance(self,NAME,INDEX,VALUE,fix=True):

        try:
    
            _object = getattr(self.sim, NAME)
            print(_object[INDEX], "was originally", _object[INDEX].value)
            _object[INDEX].value = VALUE 
            print(_object[INDEX], " is now set to ", _object[INDEX].value)


            for v in self.sim.component_objects(Var, active=True):
                if str(v)==NAME:
                    varobject = getattr(self.sim, str(v))
                    if fix == True:
                        varobject[INDEX].fixed = True
                        print("Note, ", _object[INDEX], " is now fixed")
                    if fix == False:
                        varobject[INDEX].fixed = False
                        print("Note, ", _object[INDEX], " is NOT fixed")


            print("SIM updated. Call `model_postprocess` to output or `model_solve` to solve.")  
            
        except:
            print("Unable to modify instance. Please make sure SIM instance has already been created and that you are trying to access the correct component")
    

    def model_calibrate(self, mgr, solver):
        
        
        try:
            if self.base:
                try:
                    if self.base_results:
                        print('Model already calibrated. If a SIM has been created, call `model_solve` to solve it.')
                except AttributeError:
                        with SolverManagerFactory(mgr) as solver_mgr:
                            self.base_results = solver_mgr.solve(self.base, opt=solver)
                            self.base.solutions.store_to(self.base_results)
                        
                        print("Model solved. Call `model_postprocess` to output.")
                    
            
                        if (self.base_results.solver.status == SolverStatus.ok) and (self.base_results.solver.termination_condition == TerminationCondition.optimal):
                            print('Solution is optimal and feasible')
                        elif (self.base_results.solver.termination_condition == TerminationCondition.infeasible):
                            print("Model is infeasible")
                        else:
                            print ('WARNING. Solver Status: ', self.base_results.solver)  
        except AttributeError:
            print('You must create the BASE instance before you can solve it. Call `model_instance` first.')



    def model_solve(self, mgr, solver):

        try:
            if self.base_results:
                try:
                    if self.sim:
                        with SolverManagerFactory(mgr) as solver_mgr:
                            self.sim_results = solver_mgr.solve(self.sim, opt=solver)
                            self.sim.solutions.store_to(self.sim_results)
                        
                        print("Model solved. Call `model_postprocess` to output.")
                    
            
                        if (self.sim_results.solver.status == SolverStatus.ok) and (self.sim_results.solver.termination_condition == TerminationCondition.optimal):
                            print('Solution is optimal and feasible')
                        elif (self.sim_results.solver.termination_condition == TerminationCondition.infeasible):
                            print("Model is infeasible")
                        else:
                            print ('WARNING. Solver Status: ', self.sim_results.solver)
                except AttributeError:
                    print("You must create SIM instance before you can solve it. Call `model_sim` first.")
        except AttributeError:
            print("You must first calibrate the model. Call `model_calibrate`.")


    def model_compare(self):                       
    
        try:
            if self.base:
                try:
                    if self.sim:
                                        
                        try:
                            if self.base_results:
                                try:
                                    if self.sim_results:
                                        print("#===========HERE ARE THE DIFFERENCES==========#\
                                               #===========note: both models solved==========#")
                                except:
                                        print("#===========HERE ARE THE DIFFERENCES==========#\
                                               #===========note: base model solved===========#\
                                               #===========      sim model unsolved==========#")
                        except:
                            print("#===========HERE ARE THE DIFFERENCES==========#\
                                   #===========note: both models unsolved==========#") 
                        for n in self.sim.component_objects(Var, active=True):  
                            newobject = getattr(self.sim, str(n))
                            for o in self.base.component_objects(Var, active=True):
                                oldobject = getattr(self.base, str(o))
                                if str(n)==str(o):
                                    print(newobject)
                                    for newindex in newobject:
                                        for oldindex in oldobject:
                                            if newindex == oldindex:
                                                diff = oldobject[oldindex].value - newobject[newindex].value
                                                print(newindex, diff)
                except AttributeError:
                    print("You have not created a SIM instance")
        except AttributeError:
            print("You have not created a BASE instance")


    def model_postprocess(self, object_name = "" , verbose="", base=True):
        if base == True:
            try:
                if (object_name==""):
                    print("please specify what you would like to output")
                
                elif (object_name=="instance"):
                    print_function(verbose, output=self.base.display, typename="instance")
                
                elif (object_name=="results"):
                    print_function(verbose, output=self.base_results.write, typename = "results")
                
                elif (object_name=="vars") or (object_name=="obj") or (object_name=="pickle"):
                    moment=time.strftime("%Y-%b-%d__%H_%M_%S",time.localtime())
                    if(verbose==""):
                        print("Please enter where to export to")
                    else:
                        directory = verbose
                        if not os.path.exists(directory):
                            print(directory, "directory did not exist so one was created")
                            os.makedirs(directory)
                            
                        check = os.path.abspath(os.path.join(directory, object_name))
                
                        if (object_name=="vars"):
                            print("Vars saved to: \n")
                            for v in self.base.component_objects(Var, active=True):
                                with open(check + str(v) + "_"+  moment + '.csv', 'w') as var_output:
                                    print(str(check + str(v) + "_"+  moment + '.csv'))
                                    varobject = getattr(self.base, str(v))
                                    var_output.write ('{},{} \n'.format('Names', varobject ))
                                    for index in varobject:
                                        var_output.write ('{},{} \n'.format(index, varobject[index].value))
            
                    
                        if(object_name=="obj"): 
                            with open(check + "obj_" + moment + ".csv", 'w') as obj_output:
                                obj_output.write ('{},{}\n'.format("objective", value(self.base.obj)))
                            print("Objective saved to: " + str(check + "obj_" + moment + ".csv"))
                
                        if(object_name=="pickle"):             
                            with open(check + 'saved_results_' + moment, 'wb') as pickle_output:
                                pickle.dump(self.base_results, pickle_output)
                            print("Pickled results object saved to:  " + str(check + 'saved_results_' + moment))
                    
                
                else:
                    print("Please enter a valid object_name" )
                    
            except AttributeError:
                print('Please make sure what you are trying to output has been created (base, base_results,)')
                
        if base == False:
            try:
                if (object_name==""):
                    print("please specify what you would like to output")
                
                elif (object_name=="instance"):
                    print_function(verbose, output=self.sim.display, typename="instance")
                
                elif (object_name=="results"):
                    print_function(verbose, output=self.sim_results.write, typename = "results")
                
                elif (object_name=="vars") or (object_name=="obj") or (object_name=="pickle"):
                    moment=time.strftime("%Y-%b-%d__%H_%M_%S",time.localtime())
                    if(verbose==""):
                        print("Please enter where to export to")
                    else: 
                        directory = verbose
                        if not os.path.exists(directory):
                            print(directory, "directory did not exist so one was created")
                            os.makedirs(directory)
                            
                        check = os.path.abspath(os.path.join(directory, object_name))
                
                        if (object_name=="vars"):
                            print("Vars saved to: \n")
                            for v in self.sim.component_objects(Var, active=True):
                                with open(check + str(v) + "_"+  moment + '.csv', 'w') as var_output:
                                    print(str(check + str(v) + "_"+  moment + '.csv'))
                                    varobject = getattr(self.base, str(v))
                                    var_output.write ('{},{} \n'.format('Names', varobject ))
                                    for index in varobject:
                                        var_output.write ('{},{} \n'.format(index, varobject[index].value))
            
                    
                        if(object_name=="obj"): 
                            with open(check + "obj_" + moment + ".csv", 'w') as obj_output:
                                obj_output.write ('{},{}\n'.format("objective", value(self.sim.obj)))
                            print("Objective saved to: " + str(check + "obj_" + moment + ".csv"))
                
                        if(object_name=="pickle"):             
                            with open(check + 'saved_results_' + moment, 'wb') as pickle_output:
                                pickle.dump(self.sim_results, pickle_output)
                            print("Pickled results object saved to:  " + str(check + 'saved_results_' + moment))
                            
            except AttributeError:
                print('Please make sure what you are trying to output has been created (sim, sim_results,)')
                    



    
    def model_load_results(self, pathname):
        
        if not os.path.exists(pathname):
            print(pathname, " does not exist. Please enter a valid path to the file you would like to load")
        
        else:
            
            try:

                with open(pathname, 'rb') as pkl_file:
                    loadedResults = pickle.load(pkl_file)
                    self.base.solutions.load_from(loadedResults)
                    print("results from: ", pathname, " were loaded to BASE instance")
            
            except:
                
                print("Unable to load file. Please make sure correct file is specified. Must be pickled.")
    
def print_function (verbose="", output = "", typename=""):
    
    if (verbose==""):
        print("Please specify how you would like to output")            
    elif (verbose=="print"):
        print("\nThis is the " + typename + "\n")
        output()
        print("Output printed")            
    else:            
        moment=time.strftime("%Y-%b-%d__%H_%M_%S",time.localtime())
        directory = (verbose)
        if not os.path.exists(directory):
            print(verbose, "directory did not exist so one was created")
            os.makedirs(directory)
        
        check = os.path.abspath(os.path.join(directory, typename))
            
        with open(check + moment, 'w') as output_file:
            output_file.write("\nThis is the " + typename + "\n" )
            output(ostream=output_file)
        print("Output saved to: " + str(check + moment))