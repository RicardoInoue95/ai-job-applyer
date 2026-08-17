
from pydantic import BaseModel, Field


class Experiencia(BaseModel):
    empresa: str
    cargo: str
    data_inicio: str | None = None
    data_fim: str | None = None
    descricao: str = ""
    tecnologias: list[str] = Field(default_factory=list)
    conquistas: list[str] = Field(default_factory=list)


class Formacao(BaseModel):
    instituicao: str
    curso: str
    data_conclusao: str | None = None
    em_andamento: bool = False


class Certificacao(BaseModel):
    nome: str
    emissor: str = ""
    data: str | None = None
    link: str | None = None


class Idioma(BaseModel):
    nome: str
    nivel: str = ""


class ResumeJSON(BaseModel):
    nome: str
    email: str | None = None
    telefone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    localizacao: str | None = None
    resumo_profissional: str | None = None
    experiencias: list[Experiencia] = Field(default_factory=list)
    formacao: list[Formacao] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)


class PerfilBase(BaseModel):
    perfil: str
    nome: str
    email: str | None = None
    linkedin: str | None = None
    localizacao: str | None = None
    resumo_profissional: str = ""
    experiencias: list[Experiencia] = Field(default_factory=list)
    formacao: list[Formacao] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
