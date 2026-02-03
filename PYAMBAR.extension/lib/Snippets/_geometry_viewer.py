# -*- coding: utf-8 -*-

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#==================================================
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
import sys
import System
from System import Array
from System.Collections.Generic import *

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

def bb_to_solid(bbox):
    """Converte um BoundingBoxXYZ num objeto Solid que pode ser visualizado."""
    # Pontos dos cantos inferiores do BoundingBox
    pt0 = XYZ(bbox.Min.X, bbox.Min.Y, bbox.Min.Z)
    pt1 = XYZ(bbox.Max.X, bbox.Min.Y, bbox.Min.Z)
    pt2 = XYZ(bbox.Max.X, bbox.Max.Y, bbox.Min.Z)
    pt3 = XYZ(bbox.Min.X, bbox.Max.Y, bbox.Min.Z)

    # Criar as 4 linhas que formam a base do BoundingBox
    edge0 = Line.CreateBound(pt0, pt1)
    edge1 = Line.CreateBound(pt1, pt2)
    edge2 = Line.CreateBound(pt2, pt3)
    edge3 = Line.CreateBound(pt3, pt0)

    # Criar um CurveLoop a partir das linhas
    edges = List[Curve]([edge0, edge1, edge2, edge3])
    base_loop = CurveLoop.Create(edges)
    
    # Lista de perfis para a extrusão
    loop_list = List[CurveLoop]([base_loop])

    # Calcular a altura e criar o sólido por extrusão
    altura = bbox.Max.Z - bbox.Min.Z
    # Cria o sólido na origem, sem rotação
    solido_base = GeometryCreationUtilities.CreateExtrusionGeometry(loop_list, XYZ.BasisZ, altura)

    # Aplica a transformação do BoundingBox para posicionar e rotacionar o sólido corretamente
    solido_transformado = SolidUtils.CreateTransformed(solido_base, bbox.Transform)
    
    return solido_transformado

# =================================================================
# FUNÇÃO DE VISUALIZAÇÃO DE GEOMETRIA (EXPANDIDA)
# =================================================================

def view_geometry(geometry, t= Transaction(doc, 'Visualizar Geometria'),nome_forma="Geometria Visualizada"):
    """
    Visualiza vários tipos de geometria (XYZ, Line, Solid, Face, Edge, BoundingBoxXYZ) 
    no Revit usando DirectShape.

    Args:
        geometry: Um único objeto geométrico ou uma lista de objetos.
        nome_forma (str): Um nome opcional para o DirectShape criado.
    """
    
    lista_de_geometria = List[GeometryObject]()

    if not isinstance(geometry, list):
        geometry = [geometry]

    for item in geometry:
        if isinstance(item, XYZ):
            # Converte XYZ para Point
            lista_de_geometria.Add(Point.Create(item))
        elif isinstance(item, (Line, Solid, Face, Curve)): 
            # Line, Solid, Face e outras Curves já são GeometryObjects
            lista_de_geometria.Add(item)
        elif isinstance(item, Edge):
            # Extrai a curva de uma Edge
            lista_de_geometria.Add(item.AsCurve())
        elif isinstance(item, BoundingBoxXYZ):
            # Converte o BoundingBoxXYZ para um Solid usando a função auxiliar
            solido_bbox = bb_to_solid(item)
            lista_de_geometria.Add(solido_bbox)
        else:
            print("AVISO: Item de tipo '{}' não suportado e foi ignorado.".format(type(item).__name__))

    if lista_de_geometria.Count > 0:
        t.Start()
        try:
            ds = DirectShape.CreateElement(doc, ElementId(BuiltInCategory.OST_GenericModel))
            ds.Name = nome_forma
            ds.SetShape(lista_de_geometria)
            
            t.Commit()

            return ds

        except Exception as e:
            print("ERRO ao visualizar a geometria: {}".format(e))
            if not t.HasEnded():
                t.RollBack()
    else:
        print("Nenhuma geometria válida foi fornecida para visualização.")


def view_vector(vector, origem=XYZ(0,0,0), scale=1,nome_forma="Vetor Visualizado"):
    """
    Visualiza um vetor (XYZ) como uma linha a partir de um ponto de origem.

    Args:
        vector (XYZ): O vetor a ser visualizado.
        origem (XYZ, optional): O ponto de partida para a linha do vetor. 
                                Se for None, a origem do projeto (0,0,0) é usada. 
                                Defaults to None.
        nome_forma (str): Um nome opcional para o DirectShape criado.
    """

    # Verificar se a entrada é uma lista ou um único vetor
    if isinstance(vector, list):
        vectors = vector
    else:
        vectors = [vector]

    # Tolerância mínima para Curvas
    tolerance = doc.Application.ShortCurveTolerance

    # Lista para armazenar todas as linhas
    lines = []

    # Processar cada vetor
    for i, vector in enumerate(vectors):
        if not isinstance(vector, XYZ):
            print("Erro: O item {} da entrada deve ser um objeto XYZ.".format(i))
            continue
        
        # Aplicar escala ao vetor
        vetor_escalado = vector.Multiply(scale)
        
        # Calcular ponto final do vetor
        ponto_final = origem.Add(vetor_escalado)
        
        # Verificar se a distância é maior que a tolerância
        distance = origem.DistanceTo(ponto_final)
        
        if distance < tolerance:
            print("Aviso: Vetor {} muito pequeno (distância: {:.6f}), aumentando escala".format(i, distance))
            # Criar um vetor mínimo com a tolerância
            direcao = vetor_escalado.Normalize()
            vetor_minimo = direcao.Multiply(tolerance * 2)
            ponto_final = origem.Add(vetor_minimo)
        
        try:
            # Criar a linha para visualizar o vetor
            linha = Line.CreateBound(origem, ponto_final)
            lines.append(linha)
            
        except Exception as e:
            print("Erro ao criar linha para vetor {}: {}".format(i, str(e)))
    
    # Verificar se temos linhas para visualizar
    if not lines:
        print("Nenhuma linha válida foi criada.")
        return None
    
    try:
        # Gerar o DirectShape com todas as linhas
        ds = view_geometry(lines, nome_forma=nome_forma)
        
        return ds
        
    except Exception as e:
        print("Não foi possível visualizar os vetores: {}".format(str(e)))
        return None